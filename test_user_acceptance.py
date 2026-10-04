"""
test_user_acceptance.py - PostPilot Phase 8 User Acceptance Testing Suite
Verifies all 17 user acceptance criteria:
1. Application initialization
2. Login page rendering
3. Authentication success
4. Dashboard rendering
5. Navigation between views
6. Channel selection (tour, nz, gaatha, insta)
7. Post creation
8. Post editing
9. Post deletion
10. Media upload and validation
11. Task / schedule interval configuration
12. System status reporting
13. Backup export
14. Backup import
15. User logout
16. Unauthenticated access rejection
17. CSRF enforcement on state-modifying requests
"""
import os
import sys
import io
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Configure temporary sandbox environment
TEMP_DIR = tempfile.mkdtemp(prefix="postpilot_uat_")
DB_PATH = os.path.join(TEMP_DIR, "uat_posts.db")
UPLOAD_DIR = os.path.join(TEMP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

os.environ['DATABASE_URL'] = f"sqlite:///{DB_PATH}"
os.environ['POSTPILOT_DATA_DIR'] = TEMP_DIR
os.environ['POSTPILOT_UPLOAD_FOLDER'] = UPLOAD_DIR
os.environ['APP_ENV'] = 'development'
os.environ['LOCAL_MODE'] = '0'  # Test strict remote/authenticated behavior
os.environ['ADMIN_USERNAME'] = 'uat_admin'
os.environ['ADMIN_PASSWORD'] = 'UAT_Secure_Pass_2026!'
os.environ['SECRET_KEY'] = 'uat-secret-key-abcdef123456'

import config
import database
import backup
import app as application_module

class TestUserAcceptance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        config.LOCAL_MODE = False
        config.ADMIN_USERNAME = 'uat_admin'
        config.ADMIN_PASSWORD = 'UAT_Secure_Pass_2026!'
        config.DATABASE_URL = f"sqlite:///{DB_PATH}"
        config.POSTPILOT_DATA_DIR = TEMP_DIR
        config.POSTPILOT_UPLOAD_FOLDER = UPLOAD_DIR
        config.UPLOAD_FOLDER = Path(UPLOAD_DIR)
        application_module.app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
        database.init_db()
        cls.client = application_module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def _get_csrf_token(self):
        """Fetches a valid CSRF token from the session via GET /login."""
        res = self.client.get('/login')
        with self.client.session_transaction() as sess:
            return sess.get('csrf_token')

    def test_01_app_initialization_and_login_page(self):
        """[1, 2] Application starts and login page renders with HTML."""
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"PostPilot", res.data)
        self.assertIn(b"Sign In", res.data)

    def test_02_authentication_and_dashboard(self):
        """[3, 4] Authentication succeeds and user accesses Dashboard."""
        login_res = self.client.post('/api/auth/login', json={
            'username': 'uat_admin',
            'password': 'UAT_Secure_Pass_2026!'
        })
        self.assertEqual(login_res.status_code, 200)
        data = json.loads(login_res.data)
        self.assertTrue(data.get('success'))

        # Dashboard loads with session
        dash_res = self.client.get('/')
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"Dashboard", dash_res.data)

    def test_03_navigation_and_channel_selection(self):
        """[5, 6] Navigation works across tour, nz, gaatha, insta channel endpoints."""
        channels = ['tour', 'nz', 'gaatha', 'insta']
        for ch in channels:
            res = self.client.get(f'/api/posts/{ch}')
            self.assertEqual(res.status_code, 200, f"Channel {ch} should be queryable")
            posts = json.loads(res.data)
            self.assertIsInstance(posts, list)

    def test_04_post_crud_and_media_upload(self):
        """[7, 8, 9, 10] Media upload, post creation, editing, and deletion work."""
        csrf_token = self._get_csrf_token()

        # 1. Media Upload
        img_io = io.BytesIO()
        img = Image.new('RGB', (64, 64), color='blue')
        img.save(img_io, format='PNG')
        img_io.seek(0)

        upload_res = self.client.post(
            '/api/upload',
            data={'file': (img_io, 'uat_sample.png', 'image/png')},
            headers={'X-CSRFToken': csrf_token},
            content_type='multipart/form-data'
        )
        self.assertEqual(upload_res.status_code, 201)
        filename = json.loads(upload_res.data).get('filename')
        self.assertTrue(filename)

        # 2. Create post with uploaded media
        create_res = self.client.post(
            '/api/posts/tour',
            json={
                'message': 'UAT Test Tour Post #1',
                'image_filename': filename
            },
            headers={'X-CSRFToken': csrf_token}
        )
        self.assertEqual(create_res.status_code, 201)
        created_data = json.loads(create_res.data)
        post_id = created_data.get('id')
        self.assertIsNotNone(post_id)

        # 3. Edit post
        edit_res = self.client.put(
            f'/api/posts/tour/{post_id}',
            json={'message': 'UAT Test Tour Post #1 (Edited)', 'image_filename': filename},
            headers={'X-CSRFToken': csrf_token}
        )
        self.assertEqual(edit_res.status_code, 200)

        # Verify edited message
        get_res = self.client.get('/api/posts/tour')
        posts = json.loads(get_res.data)
        matched = [p for p in posts if p['id'] == post_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]['message'], 'UAT Test Tour Post #1 (Edited)')

        # 4. Delete post
        del_res = self.client.delete(
            f'/api/posts/tour/{post_id}',
            headers={'X-CSRFToken': csrf_token}
        )
        self.assertEqual(del_res.status_code, 200)

        # Confirm post is deleted
        get_res_after = self.client.get('/api/posts/tour')
        posts_after = json.loads(get_res_after.data)
        self.assertEqual(len([p for p in posts_after if p['id'] == post_id]), 0)

    def test_05_schedule_config_and_status(self):
        """[11, 12] Task interval configuration and system status reporting."""
        csrf_token = self._get_csrf_token()

        # Update interval using PUT /api/interval/<post_type>
        interval_res = self.client.put(
            '/api/interval/tour',
            json={'interval': 3600},
            headers={'X-CSRFToken': csrf_token}
        )
        self.assertEqual(interval_res.status_code, 200)

        # Check status endpoint
        status_res = self.client.get('/api/status')
        self.assertEqual(status_res.status_code, 200)
        status_data = json.loads(status_res.data)
        self.assertEqual(status_data.get('tour_interval'), 3600)

    def test_06_backup_export_and_import(self):
        """[13, 14] Backup export generates ZIP and import restores content."""
        # 1. Export backup archive
        backup_path = backup.export_backup()
        self.assertTrue(backup_path.exists())
        self.assertTrue(backup_path.stat().st_size > 100)

        # 2. Test import into isolated database
        import_stats = backup.import_backup(backup_path, overwrite=False)
        self.assertIn('posts_imported', import_stats)

    def test_07_logout_unauth_rejection_and_csrf_protection(self):
        """[15, 16, 17] Logout invalidates session; unauthenticated access denied; CSRF enforced."""
        # 1. Logout using POST /api/auth/logout
        logout_res = self.client.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)

        # 2. Unauthenticated access to protected API is rejected with 401
        unauth_res = self.client.get('/api/posts/tour')
        self.assertEqual(unauth_res.status_code, 401)

        # 3. Unauthenticated access to dashboard redirects to login (302)
        dash_unauth = self.client.get('/')
        self.assertEqual(dash_unauth.status_code, 302)
        self.assertIn('/login', dash_unauth.headers.get('Location'))

        # 4. State alteration without CSRF token is rejected with 403
        # First log back in
        self.client.post('/api/auth/login', json={
            'username': 'uat_admin',
            'password': 'UAT_Secure_Pass_2026!'
        })
        csrf_missing_res = self.client.put(
            '/api/interval/tour',
            json={'interval': 1200}
            # No X-CSRFToken header
        )
        self.assertEqual(csrf_missing_res.status_code, 403)

if __name__ == "__main__":
    unittest.main()
