"""
PostPilot Meta / Facebook Graph API Validation Suite
Tests Meta Graph API connectivity, token verification, permission auditing,
page resolution, and error handling without printing or exposing access tokens.

CRITICAL SECURITY RULE:
- NEVER print, log, or serialize access tokens.
- Mask or omit tokens in all outputs.
"""
import os
import sys
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
import facebook_api

def run_meta_api_validation():
    print("=" * 65)
    print(" POSTPILOT META / FACEBOOK GRAPH API VALIDATION")
    print("=" * 65)

    token = facebook_api.get_access_token()
    
    # 1. Environment & Absence Check
    print("[1/5] Checking Token Configuration...")
    if not token:
        print("  [NOTICE] FB_ACCESS_TOKEN is not configured in .env or environment.")
        print("  [OK] Graceful handling: get_access_token() returns None without crashing.")
        print("  [OK] get_page_token(None, page_id) handled safely without exceptions.")
        assert facebook_api.get_page_token(None, "12345") is None
        assert facebook_api.get_token_info(None) is None
        print("  [RESULT] Offline/Safe-absence validation passed.")
        print("=" * 65)
        return {'status': 'UNCONFIGURED', 'token_valid': False, 'reason': 'FB_ACCESS_TOKEN not set'}

    print("  [OK] Token detected in environment/configuration.")
    print(f"  [OK] Token length: {len(token)} characters (Value strictly concealed)")

    # 2. Token Debug & Expiration Verification
    print("[2/5] Validating Token with Meta Debug API (v19.0)...")
    debug_url = f"{facebook_api.BASE_URL}/debug_token"
    params = {'input_token': token, 'access_token': token}
    
    try:
        resp = requests.get(debug_url, params=params, timeout=15)
        debug_data = resp.json()
    except Exception as e:
        print(f"  [NETWORK ERROR] Could not reach Meta Graph API: {e}")
        return {'status': 'NETWORK_ERROR', 'error': str(e)}

    if 'error' in debug_data:
        err = debug_data['error']
        print(f"  [API ERROR] Meta API returned error: {err.get('message')} (Code: {err.get('code')})")
        return {'status': 'INVALID_TOKEN', 'error': err.get('message'), 'code': err.get('code')}

    data = debug_data.get('data', {})
    is_valid = data.get('is_valid', False)
    app_id = data.get('app_id')
    user_id = data.get('user_id')
    expires_at = data.get('expires_at', 0)
    scopes = data.get('scopes', [])

    print(f"  [OK] Token is_valid: {is_valid}")
    print(f"  [INFO] App ID: {app_id} | User ID: {user_id}")
    if expires_at == 0:
        print("  [INFO] Token Expiration: Never (Page / System Token)")
    else:
        import datetime
        exp_dt = datetime.datetime.fromtimestamp(expires_at)
        print(f"  [INFO] Token Expiration: {exp_dt} UTC")

    # 3. Permissions / Scope Auditing
    print("[3/5] Auditing Granted Permissions / Scopes...")
    print(f"  [INFO] Total scopes granted: {len(scopes)}")
    for s in sorted(scopes):
        print(f"    - {s}")

    critical_scopes = ['pages_show_list', 'pages_read_engagement', 'pages_manage_posts']
    missing_critical = [s for s in critical_scopes if s not in scopes]
    if missing_critical:
        print(f"  [WARNING] Missing critical permissions for automated posting: {missing_critical}")
    else:
        print("  [OK] All core Facebook Page posting permissions are present.")

    # 4. User Profile & Rate Limits (/me)
    print("[4/5] Checking Account Profile & Rate Limits...")
    me_url = f"{facebook_api.BASE_URL}/me"
    try:
        me_resp = requests.get(me_url, params={'access_token': token}, timeout=15)
        me_data = me_resp.json()
        if 'error' in me_data:
            print(f"  [API ERROR] /me returned error: {me_data['error'].get('message')}")
        else:
            print(f"  [OK] Connected User/Entity: {me_data.get('name')} (ID: {me_data.get('id')})")
        
        usage = me_resp.headers.get('x-app-usage')
        if usage:
            print(f"  [INFO] App Rate Limit Usage: {usage}")
    except Exception as e:
        print(f"  [ERROR] Failed to query /me endpoint: {e}")

    # 5. Page Token Resolution (/me/accounts)
    print("[5/5] Resolving Connected Facebook Pages...")
    accounts_url = f"{facebook_api.BASE_URL}/me/accounts"
    resolved_pages = []
    try:
        acc_resp = requests.get(accounts_url, params={'access_token': token}, timeout=15)
        acc_data = acc_resp.json()
        pages = acc_data.get('data', [])
        print(f"  [INFO] Found {len(pages)} managed Facebook Page(s):")
        for p in pages:
            p_name = p.get('name')
            p_id = p.get('id')
            has_page_token = bool(p.get('access_token'))
            resolved_pages.append({'name': p_name, 'id': p_id, 'has_token': has_page_token})
            print(f"    - Page: '{p_name}' (ID: {p_id}) -> Page Token Resolved: {has_page_token}")
    except Exception as e:
        print(f"  [ERROR] Failed to query /me/accounts: {e}")

    print("=" * 65)
    print(">>> META GRAPH API VALIDATION COMPLETE <<<")
    print("=" * 65)

    return {
        'status': 'VALID' if is_valid else 'INVALID',
        'is_valid': is_valid,
        'app_id': app_id,
        'user_id': user_id,
        'scopes': scopes,
        'missing_critical_scopes': missing_critical,
        'resolved_pages': resolved_pages
    }

if __name__ == '__main__':
    run_meta_api_validation()
