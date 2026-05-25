from django.db import models
from django.utils import timezone

class Tenant(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PlantLookup(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='plants')
    plant_code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    grid_emission_factor = models.DecimalField(max_digits=10, decimal_places=4, help_text="kg CO2e per kWh")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'plant_code')

    def __str__(self):
        return f"{self.plant_code} - {self.name} ({self.country})"


class AirportLookup(models.Model):
    iata_code = models.CharField(max_length=10, unique=True)
    airport_name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    def __str__(self):
        return f"{self.iata_code} - {self.airport_name}"


class EmissionFactor(models.Model):
    SCOPE_CHOICES = (
        ('Scope 1', 'Scope 1'),
        ('Scope 2', 'Scope 2'),
        ('Scope 3', 'Scope 3'),
    )
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=255, unique=True) # e.g. 'Fuel - Diesel', 'Flight - Economy', 'Hotel - Stay'
    factor = models.DecimalField(max_digits=12, decimal_places=6, help_text="kg CO2e per unit")
    unit = models.CharField(max_length=50, help_text="Base unit, e.g., L, kWh, p-km, room-night")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.category} ({self.scope}): {self.factor} kg CO2e/{self.unit}"


class IngestionJob(models.Model):
    SOURCE_CHOICES = (
        ('SAP', 'SAP ERP (Fuel & Procurement)'),
        ('UTILITY', 'Utility Portal CSV (Electricity)'),
        ('TRAVEL', 'Corporate Travel Platform'),
    )
    STATUS_CHOICES = (
        ('SUCCESS', 'Success'),
        ('PARTIAL', 'Partial (Some errors)'),
        ('FAILED', 'Failed'),
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_jobs')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='SUCCESS')
    file_name = models.CharField(max_length=255)
    row_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.source_type} Job #{self.id} for {self.tenant.name} ({self.status})"


class RawSourceRecord(models.Model):
    ingestion_job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='raw_records')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    row_index = models.IntegerField()
    raw_data = models.JSONField(help_text="Original unmodified CSV row payload")
    processed_status = models.CharField(max_length=20, default='PENDING') # PENDING, PROCESSED, ERROR
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Raw Row {self.row_index} - Job {self.ingestion_job_id}"


class NormalizedActivity(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('FLAGGED', 'Flagged'),
        ('ERROR', 'Error'),
    )
    SCOPE_CHOICES = (
        ('Scope 1', 'Scope 1'),
        ('Scope 2', 'Scope 2'),
        ('Scope 3', 'Scope 3'),
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='activities')
    ingestion_job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='activities', null=True, blank=True)
    raw_record = models.ForeignKey(RawSourceRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='normalized_activities')
    
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=255) # normalized category name
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit = models.CharField(max_length=50) # normalized unit
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4)
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Source Tracking Metadata
    plant_code = models.CharField(max_length=50, blank=True, null=True)
    origin_airport = models.CharField(max_length=10, blank=True, null=True)
    destination_airport = models.CharField(max_length=10, blank=True, null=True)
    cabin_class = models.CharField(max_length=50, blank=True, null=True)
    hotel_nights = models.IntegerField(blank=True, null=True)
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    validation_issues = models.JSONField(default=list, blank=True, help_text="List of validation strings or code issues")
    original_data = models.JSONField(default=dict, blank=True, help_text="A clean dictionary of original headers/values for visual inspection")
    
    # Audit trail
    is_locked = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=255, blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.scope} | {self.category} | {self.quantity} {self.unit} ({self.co2e_kg} kg CO2e)"

    class Meta:
        ordering = ['-created_at']


class AuditLog(models.Model):
    normalized_activity = models.ForeignKey(NormalizedActivity, on_delete=models.CASCADE, related_name='audit_logs')
    changed_by = models.CharField(max_length=255, default='System')
    changed_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100) # e.g. 'quantity', 'status'
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    reason = models.TextField(help_text="Rationale for the adjustment")

    def __str__(self):
        return f"{self.field_name} changed from '{self.old_value}' to '{self.new_value}' on activity #{self.normalized_activity_id}"
