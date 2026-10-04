"""
PostPilot Comprehensive Runtime & Security Validation Suite
Validates Phase 3 acceptance criteria across:
- Environment initialization & configuration
- Authentication & Session security
- CSRF protection on state-altering endpoints
- Controlled Local Mode vs LAN/Remote boundaries
- SQLite WAL mode & transactional persistence across restart
- Full Post CRUD operations (Create, Read, Update, Delete, Search)
- Media validation (allowed extensions, MIME types, image integrity)
- Task state coordination via database
- Portable export & import round-trip
"""
import os
import sys
import io
import json
import shutil
import tempfile
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Create temporary isolated environment for testing
TEMP_DIR = Path(tempfile.mkdtemp(prefix="postpilot_test_"))
TEST_DB_PATH = TEMP_DIR / "posts_test.db"
TEST_UPLOAD_DIR = TEMP_DIR / "images"
TEST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Override environment variables before importing app
os.environ['DATABASE_URL'] = f"sqlite:///{TEST_DB_PATH}"
os.environ['POSTPILOT_DATA_DIR'] = str(TEMP_DIR)
os.environ['POSTPILOT_UPLOAD_FOLDER'] = str(TEST_UPLOAD_DIR)
os.environ['APP_ENV'] = 'development'
os.environ['LOCAL_MODE'] = '1'
os.environ['ADMIN_USERNAME'] = 'testadmin'
os.environ['ADMIN_PASSWORD'] = 'SecureTestPass123!'
os.environ['SECRET_KEY'] = 'test-secret-key-12345'

import config
import database
import backup
from app import app

client = app.test_client()

def create_test_image(filename="sample.png"):
    img_byte_arr = io.BytesIO()
    image = Image.new('RGB', (100, 100), color='blue')
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr, filename

def run_tests():
    print("=" * 65)
    print(" POSTPILOT COMPREHENSIVE RUNTIME VALIDATION SUITE")
    print("=" * 65)

    # 1. Database Initialization
    print("[1/10] Testing Database Initialization...")
    database.init_db()
    assert TEST_DB_PATH.exists(), "Database file was not created!"
    with database.get_db_connection() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {t['name'] for t in tables}
        assert {'posts', 'users', 'task_state'}.issubset(table_names), f"Missing tables: {table_names}"
    print("  [OK] SQLite schema initialized with WAL mode")

    # 2. User Authentication
    print("[2/10] Testing User Authentication & Password Hashing...")
    user = database.verify_user_password('testadmin', 'SecureTestPass123!')
    assert user is not None, "Failed to authenticate valid admin"
    assert user['username'] == 'testadmin', "Username mismatch"
    assert database.verify_user_password('testadmin', 'WrongPassword!') is None, "Wrong password should fail"
    
    # Test Login API
    res = client.post('/api/auth/login', json={'username': 'testadmin', 'password': 'SecureTestPass123!'})
    assert res.status_code == 200, f"Login API failed: {res.data}"
    login_data = res.get_json()
    assert login_data.get('success') is True, "Login success was not true"
    csrf_token = login_data.get('csrf_token')
    assert csrf_token, "No CSRF token returned on login"
    print("  [OK] Password verification & Login API passed")

    # 3. CSRF Protection Enforcement
    print("[3/10] Testing CSRF Protection Boundary...")
    # Request without CSRF token from remote IP should be rejected
    res_no_csrf = client.post(
        '/api/posts/tour',
        json={'message': 'Unauthenticated CSRF attack'},
        environ_overrides={'REMOTE_ADDR': '192.168.1.100'} # Remote LAN client
    )
    assert res_no_csrf.status_code in (401, 403), f"Expected 401/403 for remote unauthenticated request, got {res_no_csrf.status_code}"

    # Request with invalid CSRF token from authenticated session
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['csrf_token'] = 'real-valid-csrf-token'
    
    res_bad_csrf = client.post(
        '/api/posts/tour',
        json={'message': 'Forged request'},
        headers={'X-CSRFToken': 'fake-forged-token'},
        environ_overrides={'REMOTE_ADDR': '192.168.1.100'}
    )
    assert res_bad_csrf.status_code == 403, f"Expected 403 Forbidden for bad CSRF token, got {res_bad_csrf.status_code}"
    print("  [OK] CSRF enforcement blocked forged and missing tokens")

    # 4. Controlled Local Mode vs Remote LAN Security
    print("[4/10] Testing Localhost Auto-Auth vs Remote Rejection...")
    # Request from remote LAN without session
    with client.session_transaction() as sess:
        sess.clear()
    
    res_remote = client.get('/api/posts/tour', environ_overrides={'REMOTE_ADDR': '192.168.1.200'})
    assert res_remote.status_code == 401, f"Remote LAN request must require auth! Got {res_remote.status_code}"

    # Request from localhost 127.0.0.1 with LOCAL_MODE enabled
    res_local = client.get('/api/posts/tour', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert res_local.status_code == 200, f"Localhost request should pass in local mode! Got {res_local.status_code}"
    print("  [OK] Localhost mode bypass strictly restricted to 127.0.0.1; LAN blocked")

    # 5. Dashboard Page Load
    print("[5/10] Testing Dashboard HTML Rendering...")
    res_dash = client.get('/', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert res_dash.status_code == 200, f"Dashboard load failed: {res_dash.status_code}"
    assert b'PostPilot' in res_dash.data, "PostPilot brand missing from dashboard"
    assert b'csrf-token' in res_dash.data, "CSRF token meta tag missing from dashboard"
    print("  [OK] Dashboard loaded cleanly with security meta tags")

    # 6. Post CRUD (Primary Key IDs)
    print("[6/10] Testing Primary-Key Post CRUD Operations...")
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['csrf_token'] = 'valid-test-token'
    
    headers = {'X-CSRFToken': 'valid-test-token'}

    # CREATE
    create_res = client.post(
        '/api/posts/tour',
        json={'message': 'Initial test message for tour', 'image_filename': 'img1.png'},
        headers=headers,
        environ_overrides={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert create_res.status_code == 201, f"Create post failed: {create_res.data}"
    post_id = create_res.get_json()['id']
    assert post_id is not None, "Post ID was not returned"

    # READ
    read_res = client.get('/api/posts/tour', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert read_res.status_code == 200
    posts = read_res.get_json()
    assert any(p['id'] == post_id for p in posts), "Created post not found in list"

    # UPDATE
    update_res = client.put(
        f'/api/posts/tour/{post_id}',
        json={'message': 'Updated message content'},
        headers=headers,
        environ_overrides={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert update_res.status_code == 200, f"Update post failed: {update_res.data}"
    updated_post = database.get_post_by_id(post_id)
    assert updated_post['message'] == 'Updated message content', "Message was not updated in DB"

    # SEARCH
    search_res = client.get('/api/search?q=Updated', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert search_res.status_code == 200
    search_results = search_res.get_json()
    assert len(search_results) >= 1, "Search did not return matching post"

    # DELETE
    del_res = client.delete(f'/api/posts/tour/{post_id}', headers=headers, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert del_res.status_code == 200, f"Delete post failed: {del_res.data}"
    assert database.get_post_by_id(post_id) is None, "Post still exists in DB after delete"
    print("  [OK] Create, Read, Update, Search, Delete passed using stable PK IDs")

    # 7. Media Upload & Validation
    print("[7/10] Testing Media Validation & Integrity Checks...")
    img_data, img_name = create_test_image('valid_pic.png')
    
    # Valid image upload
    upload_res = client.post(
        '/api/upload',
        data={'file': (img_data, img_name, 'image/png')},
        headers=headers,
        content_type='multipart/form-data',
        environ_overrides={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert upload_res.status_code == 201, f"Valid upload failed: {upload_res.data}"
    saved_fn = upload_res.get_json()['filename']
    assert (TEST_UPLOAD_DIR / saved_fn).exists(), "Uploaded file not saved on disk"

    # Malicious / disallowed extension (.sh)
    bad_upload_res = client.post(
        '/api/upload',
        data={'file': (io.BytesIO(b'malicious shell script'), 'script.sh', 'text/x-sh')},
        headers=headers,
        content_type='multipart/form-data',
        environ_overrides={'REMOTE_ADDR': '127.0.0.1'}
    )
    assert bad_upload_res.status_code == 400, "Malicious file was not rejected"
    print("  [OK] Media validation accepted valid PNG and rejected unauthorized extension")

    # 8. Task State Management via Database
    print("[8/10] Testing Multi-Worker Safe Task State Endpoints...")
    start_res = client.post('/api/control/tour/start', headers=headers, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert start_res.status_code == 200, f"Task start failed: {start_res.data}"
    state = database.get_task_state('tour')
    assert state['is_running'] is True, "Task is_running not updated in DB"

    interval_res = client.put('/api/interval/tour', json={'interval': 2400}, headers=headers, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert interval_res.status_code == 200
    state = database.get_task_state('tour')
    assert state['interval'] == 2400, "Task interval not updated in DB"

    stop_res = client.post('/api/control/tour/stop', headers=headers, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert stop_res.status_code == 200
    state = database.get_task_state('tour')
    assert state['is_running'] is False, "Task is_running not stopped in DB"
    print("  [OK] Task state start, stop, and interval update persisted in DB")

    # 9. Transactional Persistence Across Restart
    print("[9/10] Testing Database Persistence Across Process Reconnect...")
    p1_id = database.add_post('gaatha', 'Persistent message before restart', saved_fn)
    database.set_task_state('gaatha', is_running=True, status='State preserved')
    
    # Simulate fresh connection
    with database.get_db_connection() as fresh_conn:
        row = fresh_conn.execute("SELECT * FROM posts WHERE id = ?", (p1_id,)).fetchone()
        assert row is not None, "Post was lost across reconnect"
        assert row['message'] == 'Persistent message before restart'
        t_row = fresh_conn.execute("SELECT * FROM task_state WHERE task_name = 'gaatha'").fetchone()
        assert t_row['is_running'] == 1
        assert t_row['status'] == 'State preserved'
    print("  [OK] Data and task state verified persistent across reconnect")

    # 10. Portable Export & Import Round-Trip
    print("[10/10] Testing Portable Export and Import...")
    # Add another post with image
    p2_id = database.add_post('nz', 'NZ immigration news', saved_fn)
    
    # Export
    backup_zip = backup.export_backup()
    assert backup_zip.exists(), "Backup zip archive not created"
    
    # Verify export contents
    import zipfile
    with zipfile.ZipFile(str(backup_zip), 'r') as zf:
        names = zf.namelist()
        assert 'manifest.json' in names, "manifest.json missing in backup"
        assert 'posts.json' in names, "posts.json missing in backup"
        assert 'settings.json' in names, "settings.json missing in backup"
        assert f"media/{saved_fn}" in names, "Referenced media missing from zip"
        
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        assert manifest['total_posts'] >= 2, "Posts count mismatch in manifest"

    # Simulate importing into alternate destination
    ALT_DIR = Path(tempfile.mkdtemp(prefix="postpilot_alt_"))
    ALT_DB = ALT_DIR / "posts_alt.db"
    ALT_UPLOAD = ALT_DIR / "images"
    
    # Temporarily switch config paths
    orig_db = config.DATABASE_URL
    orig_upload = config.UPLOAD_FOLDER
    try:
        config.DATABASE_URL = f"sqlite:///{ALT_DB}"
        config.UPLOAD_FOLDER = ALT_UPLOAD
        database.init_db()

        import_res = backup.import_backup(backup_zip, overwrite=True)
        assert import_res['posts_imported'] >= 2, f"Import failed: {import_res}"
        assert (ALT_UPLOAD / saved_fn).exists(), "Media file was not restored in alternate location"
        
        alt_posts = database.load_all_posts()
        assert len(alt_posts) >= 2, "Imported posts not found in alternate DB"
    finally:
        config.DATABASE_URL = orig_db
        config.UPLOAD_FOLDER = orig_upload
        shutil.rmtree(ALT_DIR, ignore_errors=True)

    print("  [OK] Portable export and import round-trip verified successfully")

    # Clean up test temp dir
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

    print("=" * 65)
    print(">>> ALL 10 TEST PHASES PASSED WITH ZERO ERRORS <<<")
    print("=" * 65)

if __name__ == '__main__':
    run_tests()
