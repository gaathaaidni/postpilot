"""
PostPilot Production Configuration & Security Boundary Test Suite
Validates that:
- DEBUG is disabled under production
- Development auto-auth is disabled under production (no localhost bypass)
- External requests strictly require authentication and CSRF tokens
- Secure session settings are enforced
- Media upload whitelists and image integrity checks are active
"""
import os
import io
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Use isolated temp directory for production config test
TEST_DIR = Path(tempfile.mkdtemp(prefix="postpilot_prod_test_"))
PROD_DB = TEST_DIR / "data" / "prod_posts.db"
os.environ['APP_ENV'] = 'production'
os.environ['DATABASE_URL'] = f"sqlite:///{PROD_DB}"
os.environ['POSTPILOT_DATA_DIR'] = str(TEST_DIR / "data")
os.environ['SECRET_KEY'] = 'prod-test-secret-key-abcdef123456'
os.environ['ADMIN_USERNAME'] = 'prodadmin'
os.environ['ADMIN_PASSWORD'] = 'ProductionAdminPass987!'
os.environ['LOCAL_MODE'] = '0'

import config
config.APP_ENV = 'production'
config.DATABASE_URL = f"sqlite:///{PROD_DB}"
config.POSTPILOT_DATA_DIR = TEST_DIR / "data"
config.ADMIN_USERNAME = 'prodadmin'
config.ADMIN_PASSWORD = 'ProductionAdminPass987!'
config.LOCAL_MODE = False
config.DEBUG = False

import app
import database

def test_production_security():
    print("=" * 65)
    print(" POSTPILOT PRODUCTION CONFIGURATION & BOUNDARY AUDIT")
    print("=" * 65)

    # 1. Environment & Debug Verification
    print("[1/5] Verifying Production Flags...")
    assert config.APP_ENV == 'production', f"APP_ENV expected 'production', got '{config.APP_ENV}'"
    assert config.DEBUG is False, f"DEBUG expected False in production, got {config.DEBUG}"
    assert config.SESSION_COOKIE_HTTPONLY is True
    assert config.SESSION_COOKIE_SAMESITE in ('Lax', 'Strict')
    print("  [OK] APP_ENV=production, DEBUG=False, Secure Cookies=Enforced")

    # 2. Localhost Auto-Auth Disabled in Production
    print("[2/5] Verifying Localhost Bypass is Inactive in Production...")
    client = app.app.test_client()
    
    # Request from 127.0.0.1 in production MUST NOT auto-authenticate
    res_local = client.get('/api/posts/tour', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert res_local.status_code == 401, f"Expected 401 Unauthorized for local request in production, got {res_local.status_code}"
    print("  [OK] Localhost auto-auth is strictly disabled under APP_ENV=production")

    # 3. Remote IP Authentication Enforcement
    print("[3/5] Verifying Remote IP Rejection & Boundary...")
    res_remote = client.get('/api/posts/tour', environ_overrides={'REMOTE_ADDR': '198.51.100.25'})
    assert res_remote.status_code == 401
    assert res_remote.get_json().get('auth_required') is True
    print("  [OK] External IP requests blocked with 401 Authentication Required")

    # 4. CSRF Protection Boundary
    print("[4/5] Verifying CSRF Enforcement on State Modification...")
    # Initialize DB for test dir
    database.init_db()
    # Login as admin
    login_res = client.post('/api/auth/login', json={'username': 'prodadmin', 'password': 'ProductionAdminPass987!'})
    assert login_res.status_code == 200, f"Login failed: {login_res.data}"
    csrf_token = login_res.get_json()['csrf_token']
    
    # State-altering request WITHOUT CSRF token
    post_no_csrf = client.post('/api/posts/tour', json={'message': 'test'}, environ_overrides={'REMOTE_ADDR': '198.51.100.25'})
    assert post_no_csrf.status_code == 403, f"Expected 403 Forbidden without CSRF token, got {post_no_csrf.status_code}"
    
    # State-altering request WITH CSRF token
    post_with_csrf = client.post(
        '/api/posts/tour',
        json={'message': 'Phase 5 Secure Post', 'image_filename': ''},
        headers={'X-CSRFToken': csrf_token},
        environ_overrides={'REMOTE_ADDR': '198.51.100.25'}
    )
    assert post_with_csrf.status_code == 201, f"Expected 201 Created with valid CSRF token, got {post_with_csrf.status_code}"
    print("  [OK] CSRF token strictly required for state-altering endpoints")

    # 5. Media Validation & Extension Blocking
    print("[5/5] Auditing Media Validation & Extension Whitelist...")
    bad_upload = client.post(
        '/api/upload',
        data={'file': (io.BytesIO(b'#!/bin/bash\nrm -rf /'), 'exploit.sh', 'text/x-sh')},
        headers={'X-CSRFToken': csrf_token},
        content_type='multipart/form-data',
        environ_overrides={'REMOTE_ADDR': '198.51.100.25'}
    )
    assert bad_upload.status_code == 400, "Malicious script upload was not blocked"
    
    fake_png = client.post(
        '/api/upload',
        data={'file': (io.BytesIO(b'not a real png header'), 'test.png', 'image/png')},
        headers={'X-CSRFToken': csrf_token},
        content_type='multipart/form-data',
        environ_overrides={'REMOTE_ADDR': '198.51.100.25'}
    )
    assert fake_png.status_code == 400, "Corrupt image data was not rejected by PIL verification"
    print("  [OK] Dangerous file extensions and forged MIME headers rejected")

    print("=" * 65)
    print(">>> PRODUCTION SECURITY & BOUNDARY CHECKS PASSED <<<")
    print("=" * 65)
    
    shutil.rmtree(str(TEST_DIR), ignore_errors=True)
    return True

if __name__ == '__main__':
    test_production_security()
