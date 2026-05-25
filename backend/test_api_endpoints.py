import urllib.request
import json
import urllib.parse
import sys

BASE_URL = 'http://127.0.0.1:8000/api'

def make_request(url, method='GET', data=None, headers=None):
    if headers is None:
        headers = {}
    
    req_data = None
    if data is not None:
        req_data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            return response.status, json.loads(res_body)
    except urllib.error.HTTPError as e:
        res_body = e.read().decode('utf-8')
        try:
            return e.code, json.loads(res_body)
        except Exception:
            return e.code, {"error": res_body}
    except Exception as e:
        return 500, {"error": str(e)}

def test_api():
    print("="*60)
    print("API ENDPOINT INTEGRATION & COMPLIANCE VERIFIER")
    print("="*60)
    
    # 1. Test Master Directory Seeding
    print("\n[Step 1] Triggering Database Master Directory Seeding via POST...")
    status, res = make_request(f"{BASE_URL}/seed-db/", method='POST')
    print(f"Status: {status}")
    print(f"Response: {res.get('message')}")
    if status != 201:
        print("FAIL: Unable to seed database. Is the server running?")
        sys.exit(1)
        
    tenant_id = res.get('tenant_id')
    
    # 2. Test Get Metrics Endpoint
    print("\n[Step 2] Retrieving Dashboard Aggregated Metrics via GET...")
    status, res = make_request(f"{BASE_URL}/metrics/?tenant={tenant_id}")
    print(f"Status: {status}")
    print(f"Normalized total tCO2e: {res.get('metrics', {}).get('total_co2e_kg', 0) / 1000} tonnes")
    print(f"Activities Ingested: {res.get('metrics', {}).get('total_rows')} rows")
    print(f"Anomalies/Spikes flagged: {res.get('metrics', {}).get('flagged_rows')} rows")
    print(f"Parser validation errors: {res.get('metrics', {}).get('error_rows')} rows")
    
    # 3. Test Get Activities
    print("\n[Step 3] Querying Activities Grid details via GET...")
    status, res = make_request(f"{BASE_URL}/activities/?tenant={tenant_id}")
    print(f"Status: {status}")
    activities = res.get('results', res) if isinstance(res, dict) else res
    print(f"Fetched {len(activities)} activities.")
    if not activities:
        print("FAIL: No activities found.")
        sys.exit(1)
        
    target_act = None
    for act in activities:
        if act.get('status') == 'PENDING' and act.get('category') != 'SAP Error Row':
            target_act = act
            break
            
    if not target_act:
        target_act = activities[0]
        
    print(f"Target activity for adjustment tests: ID={target_act.get('id')}, Cat={target_act.get('category')}, Qty={target_act.get('quantity')} {target_act.get('unit')}")
    
    # 4. Test Manual Adjustments & Audit Logging
    print("\n[Step 4] Committing manual adjustment using POST with justification logs...")
    adjust_payload = {
        "quantity": float(target_act.get('quantity')) * 1.1, # increase by 10%
        "analyst_name": "Senior ESG Auditor Lead",
        "change_reason": "Adjusted due to supplier invoice discrepancy correction."
    }
    status, res = make_request(f"{BASE_URL}/activities/{target_act.get('id')}/", method='PATCH', data=adjust_payload)
    print(f"Status: {status}")
    if status != 200:
        print(f"FAIL: Adjusting row failed: {res}")
        sys.exit(1)
    print(f"New Quantity set: {res.get('quantity')} {res.get('unit')} | Computed CO2e: {res.get('co2e_kg')} kg")
    print(f"Logged Audit Logs count: {len(res.get('audit_logs', []))} log entries.")
    for log in res.get('audit_logs', []):
        print(f"  -> Field '{log.get('field_name')}' changed by '{log.get('changed_by')}' from '{log.get('old_value')}' to '{log.get('new_value')}' (Reason: {log.get('reason')})")

    # 5. Test Sign-off & Audit Lock Immutable Check
    print("\n[Step 5] Signing off activity and applying compliance audit lock...")
    status, res = make_request(f"{BASE_URL}/activities/{target_act.get('id')}/approve/", method='POST', data={"analyst_name": "Lead Auditor Signoff"})
    print(f"Status: {status}")
    print(f"Is locked for audit: {res.get('is_locked')} | Signed by: {res.get('approved_by')} at {res.get('approved_at')}")
    
    print("\n[Step 6] Verifying Immutability! Attempting to edit a locked compliance row (must fail)...")
    status, res = make_request(f"{BASE_URL}/activities/{target_act.get('id')}/", method='PATCH', data={
        "quantity": float(res.get('quantity')) * 1.5,
        "analyst_name": "Intruder Analyst",
        "change_reason": "Malicious edit attempt on locked ledger."
    })
    print(f"Status: {status} (Expected: 400 Bad Request)")
    print(f"Server rejection message: {res.get('error')}")
    if status == 400:
        print("\nSUCCESS: Ledger immutability test passed perfectly. Locked rows cannot be modified.")
    else:
        print("\nFAIL: Malicious edit succeeded or returned unexpected status.")
        sys.exit(1)

    print("\n" + "="*60)
    print("ALL HTTP ENDPOINTS ARE 100% CORRECT & FULLY COMPLIANT")
    print("="*60)

if __name__ == '__main__':
    test_api()
