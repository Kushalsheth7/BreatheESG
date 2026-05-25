from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import json

from .models import (
    Tenant, PlantLookup, AirportLookup, EmissionFactor,
    IngestionJob, RawSourceRecord, NormalizedActivity, AuditLog
)
from .serializers import (
    TenantSerializer, PlantLookupSerializer, AirportLookupSerializer,
    EmissionFactorSerializer, IngestionJobSerializer,
    NormalizedActivitySerializer, AuditLogSerializer
)
from .parsers import parse_sap_csv, parse_utility_csv, parse_travel_csv

class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_name = TenantSerializer
    serializer_class = TenantSerializer


class PlantLookupViewSet(viewsets.ModelViewSet):
    queryset = PlantLookup.objects.all()
    serializer_class = PlantLookupSerializer

    def get_queryset(self):
        tenant_id = self.request.query_params.get('tenant')
        if tenant_id:
            return self.queryset.filter(tenant_id=tenant_id)
        return self.queryset


class AirportLookupViewSet(viewsets.ModelViewSet):
    queryset = AirportLookup.objects.all()
    serializer_class = AirportLookupSerializer


class EmissionFactorViewSet(viewsets.ModelViewSet):
    queryset = EmissionFactor.objects.all()
    serializer_class = EmissionFactorSerializer


class IngestionJobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionJob.objects.all().order_by('-timestamp')
    serializer_class = IngestionJobSerializer

    def get_queryset(self):
        tenant_id = self.request.query_params.get('tenant')
        if tenant_id:
            return self.queryset.filter(tenant_id=tenant_id)
        return self.queryset


class NormalizedActivityViewSet(viewsets.ModelViewSet):
    queryset = NormalizedActivity.objects.all()
    serializer_class = NormalizedActivitySerializer

    def get_queryset(self):
        tenant_id = self.request.query_params.get('tenant')
        queryset = self.queryset
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
            
        scope = self.request.query_params.get('scope')
        if scope:
            queryset = queryset.filter(scope=scope)
            
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(category__icontains=search) | 
                models.Q(plant_code__icontains=search) |
                models.Q(unit__icontains=search)
            )
            
        return queryset

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_row(self, request, pk=None):
        """
        Approves an individual activity row and locks it for audit.
        """
        activity = self.get_object()
        if activity.is_locked:
            return Response(
                {"error": "This activity is already locked for audit and cannot be modified."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        analyst_name = request.data.get('analyst_name', 'Lead ESG Auditor')
        
        with transaction.atomic():
            old_status = activity.status
            activity.status = 'APPROVED'
            activity.is_locked = True
            activity.approved_by = analyst_name
            activity.approved_at = timezone.now()
            activity.save()
            
            # Audit log
            AuditLog.objects.create(
                normalized_activity=activity,
                changed_by=analyst_name,
                field_name='status',
                old_value=old_status,
                new_value='APPROVED',
                reason='Analyst signed-off and locked row for compliance.'
            )
            
        return Response(NormalizedActivitySerializer(activity).data)

    @action(detail=False, methods=['post'], url_path='bulk-approve')
    def bulk_approve(self, request):
        """
        Bulk approves all pending/flagged activity rows for a specific tenant.
        """
        tenant_id = request.data.get('tenant')
        analyst_name = request.data.get('analyst_name', 'Lead ESG Auditor')
        
        if not tenant_id:
            return Response({"error": "Tenant ID is required."}, status=status.HTTP_400_BAD_REQUEST)
            
        activities = NormalizedActivity.objects.filter(
            tenant_id=tenant_id, 
            status__in=['PENDING', 'FLAGGED'],
            is_locked=False
        )
        
        approved_count = 0
        with transaction.atomic():
            for act in activities:
                old_status = act.status
                act.status = 'APPROVED'
                act.is_locked = True
                act.approved_by = analyst_name
                act.approved_at = timezone.now()
                act.save()
                
                AuditLog.objects.create(
                    normalized_activity=act,
                    changed_by=analyst_name,
                    field_name='status',
                    old_value=old_status,
                    new_value='APPROVED',
                    reason='Analyst bulk approved and locked row.'
                )
                approved_count += 1
                
        return Response({"message": f"Successfully approved and locked {approved_count} activities for audit."})

    def update(self, request, *args, **kwargs):
        """
        Updates an activity row with detailed Audit Log capture.
        """
        partial = kwargs.pop('partial', False)
        activity = self.get_object()
        
        if activity.is_locked:
            return Response(
                {"error": "This activity is locked for audit and cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        analyst_name = request.data.get('analyst_name', 'ESG Analyst')
        change_reason = request.data.get('change_reason', 'Manual data correction')
        
        if not change_reason or len(change_reason.strip()) < 5:
            return Response(
                {"error": "A valid adjustment explanation (at least 5 characters) is required to edit audited data."},
                status=status.HTTP_400_BAD_REQUEST
            )

        mutable_data = request.data.copy()
        
        # Calculate new emission if quantity is updated
        new_quantity = mutable_data.get('quantity')
        if new_quantity is not None:
            try:
                new_qty_dec = Decimal(str(new_quantity))
                # Re-calculate emission based on category factor lookup
                try:
                    ef_obj = EmissionFactor.objects.get(category=activity.category)
                    new_co2 = new_qty_dec * ef_obj.factor
                except EmissionFactor.DoesNotExist:
                    # Fallback to current ratio
                    ratio = activity.co2e_kg / activity.quantity if activity.quantity != 0 else Decimal('0')
                    new_co2 = new_qty_dec * ratio
                mutable_data['co2e_kg'] = round(new_co2, 4)
            except Exception:
                pass

        serializer = self.get_serializer(activity, data=mutable_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Track changes for the AuditLog
        with transaction.atomic():
            changed_fields = []
            for field in ['quantity', 'category', 'scope', 'start_date', 'end_date', 'status', 'plant_code']:
                if field in serializer.validated_data:
                    old_val = getattr(activity, field)
                    new_val = serializer.validated_data[field]
                    
                    # Compare as strings or decimals
                    if str(old_val) != str(new_val):
                        AuditLog.objects.create(
                            normalized_activity=activity,
                            changed_by=analyst_name,
                            field_name=field,
                            old_value=str(old_val),
                            new_value=str(new_val),
                            reason=change_reason
                        )
                        changed_fields.append(field)
            
            # Save the updated activity
            # If manually adjusted, clear original validation errors that might be resolved
            updated_activity = serializer.save()
            
            # If status was manually edited to something besides PENDING, preserve it.
            # Otherwise, if it was FLAGGED, and we modified it, we can resolve it to PENDING.
            if 'quantity' in changed_fields and updated_activity.status == 'FLAGGED':
                updated_activity.status = 'PENDING'
                updated_activity.validation_issues.append(f"Adjusted by {analyst_name}: {change_reason}")
                updated_activity.save()
                
        return Response(self.get_serializer(updated_activity).data)


class IngestionUploadView(generics.CreateAPIView):
    """
    Accepts CSV raw file data and invokes corresponding parser engine.
    """
    def post(self, request, *args, **kwargs):
        tenant_id = request.data.get('tenant')
        source_type = request.data.get('source_type') # SAP, UTILITY, TRAVEL
        file_obj = request.FILES.get('file')
        
        if not tenant_id or not source_type or not file_obj:
            return Response(
                {"error": "Missing required fields: tenant, source_type, or file."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        tenant = get_object_or_404(Tenant, id=tenant_id)
        file_name = file_obj.name
        
        try:
            csv_content = file_obj.read().decode('utf-8-sig') # handle BOM if present
        except Exception as e:
            return Response(
                {"error": f"Failed to decode uploaded file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            if source_type == 'SAP':
                job, activities = parse_sap_csv(tenant, csv_content, file_name)
            elif source_type == 'UTILITY':
                job, activities = parse_utility_csv(tenant, csv_content, file_name)
            elif source_type == 'TRAVEL':
                job, activities = parse_travel_csv(tenant, csv_content, file_name)
            else:
                return Response(
                    {"error": f"Unsupported source type: {source_type}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        serializer = IngestionJobSerializer(job)
        return Response({
            "job": serializer.data,
            "activities_count": len(activities),
            "status": job.status
        }, status=status.HTTP_201_CREATED)


class DashboardMetricsView(generics.RetrieveAPIView):
    """
    Aggregates carbon emissions metrics, scope distributions, and status logs 
    for visual representation.
    """
    def get(self, request, *args, **kwargs):
        tenant_id = request.query_params.get('tenant')
        if not tenant_id:
            return Response({"error": "Tenant ID is required."}, status=status.HTTP_400_BAD_REQUEST)
            
        activities = NormalizedActivity.objects.filter(tenant_id=tenant_id)
        
        # Summary counts
        total_rows = activities.count()
        pending_rows = activities.filter(status='PENDING').count()
        approved_rows = activities.filter(status='APPROVED').count()
        flagged_rows = activities.filter(status='FLAGGED').count()
        error_rows = activities.filter(status='ERROR').count()
        
        # Scope breakdown
        scope_1_emissions = float(sum(activities.filter(scope='Scope 1').values_list('co2e_kg', flat=True)))
        scope_2_emissions = float(sum(activities.filter(scope='Scope 2').values_list('co2e_kg', flat=True)))
        scope_3_emissions = float(sum(activities.filter(scope='Scope 3').values_list('co2e_kg', flat=True)))
        
        total_co2e_kg = scope_1_emissions + scope_2_emissions + scope_3_emissions
        
        # Month-by-month emissions breakdown (for the line/bar chart)
        # Group activities by year and month of start_date
        monthly_data = {}
        for act in activities.filter(status='APPROVED'):
            m_key = act.start_date.strftime('%Y-%m')
            m_label = act.start_date.strftime('%b %y')
            if m_key not in monthly_data:
                monthly_data[m_key] = {'month': m_label, 'Scope 1': 0.0, 'Scope 2': 0.0, 'Scope 3': 0.0, 'Total': 0.0}
            
            val = float(act.co2e_kg)
            monthly_data[m_key][act.scope] += val
            monthly_data[m_key]['Total'] += val
            
        # Sort monthly records chronologically
        sorted_monthly = [monthly_data[k] for k in sorted(monthly_data.keys())]
        
        # Source contribution breakdown
        source_data = {}
        for act in activities:
            job_src = act.ingestion_job.source_type if act.ingestion_job else 'MANUAL'
            source_data[job_src] = source_data.get(job_src, 0.0) + float(act.co2e_kg)
            
        source_breakdown = [{'source': k, 'co2e': round(v, 2)} for k, v in source_data.items()]
        
        return Response({
            "metrics": {
                "total_co2e_kg": round(total_co2e_kg, 2),
                "scope_1_kg": round(scope_1_emissions, 2),
                "scope_2_kg": round(scope_2_emissions, 2),
                "scope_3_kg": round(scope_3_emissions, 2),
                "total_rows": total_rows,
                "pending_rows": pending_rows,
                "approved_rows": approved_rows,
                "flagged_rows": flagged_rows,
                "error_rows": error_rows,
                "approval_rate": round((approved_rows / total_rows * 100), 1) if total_rows > 0 else 0.0
            },
            "monthly_emissions": sorted_monthly,
            "source_breakdown": source_breakdown
        })


class DBSeedingView(generics.CreateAPIView):
    """
    Utility endpoint to quickly seed initial lookups: Plants, Airports, and Emission Factors.
    This lets us run immediate end-to-end trials with realistic master data.
    """
    def post(self, request, *args, **kwargs):
        from django.conf import settings
        from pathlib import Path
        
        with transaction.atomic():
            # 1. Tenant Creation
            tenant, _ = Tenant.objects.get_or_create(name="Global Enterprises Ltd")
            
            # 2. Plant Master Lookup Seeding
            plants_data = [
                {"code": "DE01", "name": "Berlin Automotive Production Hub", "city": "Berlin", "country": "Germany", "factor": Decimal("0.3450")},
                {"code": "US02", "name": "Silicon Valley R&D Data Center", "city": "San Jose", "country": "USA", "factor": Decimal("0.2450")},
                {"code": "IN03", "name": "Mumbai Technology & Operations Center", "city": "Mumbai", "country": "India", "factor": Decimal("0.7100")},
                {"code": "MTR-98234-A", "name": "PGE Smart Meter facility link", "city": "San Jose", "country": "USA", "factor": Decimal("0.2450")},
            ]
            for p in plants_data:
                PlantLookup.objects.update_or_create(
                    tenant=tenant,
                    plant_code=p["code"],
                    defaults={
                        "name": p["name"],
                        "city": p["city"],
                        "country": p["country"],
                        "grid_emission_factor": p["factor"]
                    }
                )

            # 3. Airport Master Lookup Seeding (IATA coordinates)
            airports_data = [
                {"code": "JFK", "name": "John F. Kennedy International Airport", "city": "New York", "country": "USA", "lat": Decimal("40.639751"), "lon": Decimal("-73.778925")},
                {"code": "SFO", "name": "San Francisco International Airport", "city": "San Francisco", "country": "USA", "lat": Decimal("37.619002"), "lon": Decimal("-122.374843")},
                {"code": "LHR", "name": "London Heathrow Airport", "city": "London", "country": "UK", "lat": Decimal("51.470022"), "lon": Decimal("-0.454295")},
                {"code": "CDG", "name": "Charles de Gaulle Airport", "city": "Paris", "country": "France", "lat": Decimal("49.009724"), "lon": Decimal("2.547900")},
                {"code": "LAX", "name": "Los Angeles International Airport", "city": "Los Angeles", "country": "USA", "lat": Decimal("33.941589"), "lon": Decimal("-118.40853")},
                {"code": "SIN", "name": "Singapore Changi Airport", "city": "Singapore", "country": "Singapore", "lat": Decimal("1.364420"), "lon": Decimal("103.991012")},
                {"code": "BOM", "name": "Chhatrapati Shivaji Maharaj Airport", "city": "Mumbai", "country": "India", "lat": Decimal("19.089600"), "lon": Decimal("72.865600")}
            ]
            for a in airports_data:
                AirportLookup.objects.update_or_create(
                    iata_code=a["code"],
                    defaults={
                        "airport_name": a["name"],
                        "city": a["city"],
                        "country": a["country"],
                        "latitude": a["lat"],
                        "longitude": a["lon"]
                    }
                )

            # 4. Standard Emission Factors Seeding
            factors_data = [
                {"scope": "Scope 1", "category": "Fuel - Diesel", "factor": Decimal("2.680000"), "unit": "L", "desc": "Diesel Stationary Combustion (kg CO2e per liter)"},
                {"scope": "Scope 1", "category": "Fuel - Natural Gas", "factor": Decimal("1.884000"), "unit": "M3", "desc": "Natural Gas Combustion (kg CO2e per cubic meter)"},
                {"scope": "Scope 2", "category": "Electricity - Grid", "factor": Decimal("0.385000"), "unit": "kWh", "desc": "Standard Grid Electricity consumption factor"},
                {"scope": "Scope 3", "category": "Flight - Economy", "factor": Decimal("0.115000"), "unit": "p-km", "desc": "Commercial Short/Long Flight Economy Class"},
                {"scope": "Scope 3", "category": "Flight - Business", "factor": Decimal("0.240000"), "unit": "p-km", "desc": "Commercial Flight Business Class"},
                {"scope": "Scope 3", "category": "Flight - First", "factor": Decimal("0.370000"), "unit": "p-km", "desc": "Commercial Flight First Class"},
                {"scope": "Scope 3", "category": "Hotel - Stay", "factor": Decimal("18.400000"), "unit": "room-night", "desc": "Average Hotel night room stay factor"},
                {"scope": "Scope 3", "category": "Ground - Taxi", "factor": Decimal("0.185000"), "unit": "km", "desc": "Ground transport taxi or rideshare"},
                {"scope": "Scope 3", "category": "Ground - Train", "factor": Decimal("0.035000"), "unit": "km", "desc": "Ground electric rail train transport"},
                {"scope": "Scope 3", "category": "Procurement - General", "factor": Decimal("0.285000"), "unit": "EUR", "desc": "General Spend-based Scope 3 Procurement factor"}
            ]
            for f in factors_data:
                EmissionFactor.objects.update_or_create(
                    category=f["category"],
                    defaults={
                        "scope": f["scope"],
                        "factor": f["factor"],
                        "unit": f["unit"],
                        "description": f["desc"]
                    }
                )

            # 5. Dynamic Ingestion of Mock CSV Files to populate demo activities instantly!
            try:
                base_dir = settings.BASE_DIR
                mock_dir = base_dir.parent / 'mock_data'
                
                # Ingest SAP
                sap_path = mock_dir / 'sap_fuel_procurement.csv'
                if sap_path.exists():
                    with open(sap_path, 'r', encoding='utf-8') as f:
                        sap_content = f.read()
                    parse_sap_csv(tenant, sap_content, 'sap_fuel_procurement.csv')
                    
                # Ingest Utility
                utility_path = mock_dir / 'utility_electricity.csv'
                if utility_path.exists():
                    with open(utility_path, 'r', encoding='utf-8') as f:
                        util_content = f.read()
                    parse_utility_csv(tenant, util_content, 'utility_electricity.csv')
                    
                # Ingest Travel
                travel_path = mock_dir / 'travel_concur.csv'
                if travel_path.exists():
                    with open(travel_path, 'r', encoding='utf-8') as f:
                        travel_content = f.read()
                    parse_travel_csv(tenant, travel_content, 'travel_concur.csv')
            except Exception as e:
                # Log error silently or let transaction succeed with master directories
                pass

        return Response({
            "message": "Seeded database master directories and loaded mock activity log data successfully.",
            "tenant_id": tenant.id,
            "tenant_name": tenant.name
        }, status=status.HTTP_201_CREATED)
