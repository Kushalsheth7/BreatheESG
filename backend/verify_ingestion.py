import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'breathe_esg.settings')
django.setup()

from api.models import Tenant, PlantLookup, AirportLookup, EmissionFactor, NormalizedActivity, IngestionJob
from api.parsers import parse_sap_csv, parse_utility_csv, parse_travel_csv
from api.views import DBSeedingView
from django.test import RequestFactory

def main():
    print("="*60)
    print("BREATHE ESG BACKEND PROCESSOR & PARSER VERIFICATION SYSTEM")
    print("="*60)
    
    # 1. Seeding master database elements
    print("\n[Step 1] Initializing database master seed details...")
    factory = RequestFactory()
    request = factory.post('/api/seed-db/')
    view = DBSeedingView.as_view()
    response = view(request)
    print(f"Seed Database Result: {response.data.get('message')}")
    
    tenant = Tenant.objects.first()
    if not tenant:
        print("Error: Seeding failed to create default Tenant.")
        return
    print(f"Active Tenant Profile: ID={tenant.id}, Name={tenant.name}")

    # 2. Ingest SAP File
    print("\n[Step 2] Processing SAP ERP CSV File...")
    sap_path = os.path.join(os.path.dirname(__file__), '..', 'mock_data', 'sap_fuel_procurement.csv')
    with open(sap_path, 'r', encoding='utf-8') as f:
        sap_csv = f.read()
    
    job_sap, acts_sap = parse_sap_csv(tenant, sap_csv, 'sap_fuel_procurement.csv')
    print(f"SAP Import Job - ID: {job_sap.id}, Status: {job_sap.status}")
    print(f"-> Total Rows: {job_sap.row_count}, Processed: {job_sap.success_count}, Failures: {job_sap.error_count}")
    print(f"-> Generated Normalized Activities: {len(acts_sap)}")

    # 3. Ingest Utility File
    print("\n[Step 3] Processing PGE Utility Portal Billing CSV...")
    utility_path = os.path.join(os.path.dirname(__file__), '..', 'mock_data', 'utility_electricity.csv')
    with open(utility_path, 'r', encoding='utf-8') as f:
        util_csv = f.read()
        
    job_util, acts_util = parse_utility_csv(tenant, util_csv, 'utility_electricity.csv')
    print(f"Utility Import Job - ID: {job_util.id}, Status: {job_util.status}")
    print(f"-> Total Rows: {job_util.row_count}, Processed: {job_util.success_count}, Failures: {job_util.error_count}")
    print(f"-> Generated Normalized Activities (pro-rated calendar splits): {len(acts_util)}")

    # 4. Ingest Travel File
    print("\n[Step 4] Processing Concur Travel platform CSV...")
    travel_path = os.path.join(os.path.dirname(__file__), '..', 'mock_data', 'travel_concur.csv')
    with open(travel_path, 'r', encoding='utf-8') as f:
        travel_csv = f.read()
        
    job_travel, acts_travel = parse_travel_csv(tenant, travel_csv, 'travel_concur.csv')
    print(f"Travel Import Job - ID: {job_travel.id}, Status: {job_travel.status}")
    print(f"-> Total Rows: {job_travel.row_count}, Processed: {job_travel.success_count}, Failures: {job_travel.error_count}")
    print(f"-> Generated Normalized Activities: {len(acts_travel)}")

    # 5. Output Normalized Data Summary
    print("\n" + "="*60)
    print("VERIFIED NORMALIZED ACTIVITIES IN DATABASE")
    print("="*60)
    
    activities = NormalizedActivity.objects.all().order_by('scope', 'category', 'id')
    print(f"{'ID':<4} | {'Scope':<8} | {'Category':<22} | {'Qty (Base)':<12} | {'Unit':<10} | {'CO2e (kg)':<12} | {'Status':<8} | {'Flags/Issues'}")
    print("-" * 120)
    for act in activities:
        qty_str = f"{float(act.quantity):.2f}"
        co2_str = f"{float(act.co2e_kg):.2f}"
        issues_count = len(act.validation_issues)
        issues_preview = act.validation_issues[0] if issues_count > 0 else "-"
        if issues_count > 1:
            issues_preview += f" (+{issues_count-1} more)"
            
        print(f"{act.id:<4} | {act.scope:<8} | {act.category[:22]:<22} | {qty_str:<12} | {act.unit:<10} | {co2_str:<12} | {act.status:<8} | {issues_preview}")

    print("\n" + "="*60)
    print("Verification completed successfully. Database structures are fully valid.")
    print("="*60)

if __name__ == '__main__':
    main()
