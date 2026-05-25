from rest_framework import serializers
from .models import (
    Tenant, PlantLookup, AirportLookup, EmissionFactor,
    IngestionJob, RawSourceRecord, NormalizedActivity, AuditLog
)

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = '__all__'


class PlantLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantLookup
        fields = '__all__'


class AirportLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirportLookup
        fields = '__all__'


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = '__all__'


class IngestionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionJob
        fields = '__all__'


class RawSourceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawSourceRecord
        fields = '__all__'


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'


class NormalizedActivitySerializer(serializers.ModelSerializer):
    audit_logs = AuditLogSerializer(many=True, read_only=True)
    raw_record_error = serializers.SerializerMethodField()

    class Meta:
        model = NormalizedActivity
        fields = [
            'id', 'tenant', 'ingestion_job', 'raw_record', 'scope', 'category',
            'quantity', 'unit', 'co2e_kg', 'start_date', 'end_date',
            'plant_code', 'origin_airport', 'destination_airport', 'cabin_class',
            'hotel_nights', 'status', 'validation_issues', 'original_data',
            'is_locked', 'approved_by', 'approved_at', 'created_at', 'updated_at',
            'audit_logs', 'raw_record_error'
        ]

    def get_raw_record_error(self, obj):
        if obj.raw_record and obj.raw_record.processed_status == 'ERROR':
            return obj.raw_record.error_message
        return None
