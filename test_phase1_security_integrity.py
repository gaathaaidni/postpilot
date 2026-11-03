"""
test_phase1_security_integrity.py - PostPilot Phase 1 Reliability, Security & Data Integrity Test Suite

Verifies all Phase 1 implementation targets:
1. Channel-scoped record access (known defect resolution: cross-channel update/delete prevention)
2. Organization-scoped record access & multi-tenancy isolation
3. Database-level ownership & channel validation in queries
4. Production secrets enforcement (no silent transient generation in production)
5. CSRF, session isolation, defensive HTTP security headers, and path traversal protection
6. Token and credential leakage prevention across APIs and logs
7. Persistent calendar scheduling model with UTC timestamp standardization
8. Multi-worker atomic claiming and duplicate publishing prevention
9. Stale worker lease recovery and crash resilience
10. Idempotency key duplicate protection
11. Seeded GAATHA multi-brand workspaces & dynamic brand configuration
12. Non-destructive schema migration and index creation
"""
import os
import sys
import io
import json
import time
import tempfile
import unittest
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Configure temporary sandbox environment for Phase 1 tests
TEMP_DIR = tempfile.mkdtemp(prefix="postpilot_phase1_")
DB_PATH = os.path.join(TEMP_DIR, "phase1_posts.db")
UPLOAD_DIR = os.path.join(TEMP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

os.environ['DATABASE_URL'] = f"sqlite:///{DB_PATH}"
os.environ['POSTPILOT_DATA_DIR'] = TEMP_DIR
os.environ['POSTPILOT_UPLOAD_FOLDER'] = UPLOAD_DIR
os.environ['APP_ENV'] = 'development'
os.environ['LOCAL_MODE'] = '0'
os.environ['ADMIN_USERNAME'] = 'secadmin'
os.environ['ADMIN_PASSWORD'] = 'Phase1_SecTest_Pass!'
os.environ['SECRET_KEY'] = 'phase1-test-secret-key-abcdef123456'

import config
import database
import app as application_module
import worker


class TestPhase1SecurityAndIntegrity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        config.LOCAL_MODE = False
        config.ADMIN_USERNAME = 'secadmin'
        config.ADMIN_PASSWORD = 'Phase1_SecTest_Pass!'
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

    def _login(self, username='secadmin', password='Phase1_SecTest_Pass!'):
        """Logs in and returns the CSRF token and response data."""
        res = self.client.post('/api/auth/login', json={'username': username, 'password': password})
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        return data.get('csrf_token')

    # =========================================================================
    # 1. CHANNEL-SCOPED RECORD ACCESS & KNOWN DEFECT RESOLUTION
    # =========================================================================

    def test_01_cross_channel_update_prevention(self):
        """
        Known Defect Resolution:
        A post created under 'tour' CANNOT be updated through the 'nz' endpoint or
        with a mismatched post_type in database operations.
        """
        csrf = self._login()

        # 1. Create a genuine post under channel 'tour'
        tour_id = database.add_post('tour', 'Original Tour Message', 'tour.png', organization_id=1)
        self.assertIsNotNone(tour_id)

        # 2. Attempt to update tour_id through the 'nz' API route -> MUST FAIL (404)
        nz_update_res = self.client.put(
            f'/api/posts/nz/{tour_id}',
            json={'message': 'Illegitimate Cross-Channel Mutation'},
            headers={'X-CSRFToken': csrf}
        )
        self.assertEqual(nz_update_res.status_code, 404, "Cross-channel update must return 404 Not Found")

        # 3. Verify in database that tour post content was NOT modified
        post = database.get_post_by_id(tour_id)
        self.assertEqual(post['message'], 'Original Tour Message')
        self.assertEqual(post['post_type'], 'tour')

        # 4. Attempt direct database update with mismatched post_type -> MUST return False
        db_update_result = database.update_post_by_id(
            tour_id,
            message='Direct DB Attack',
            post_type='nz',
            organization_id=1
        )
        self.assertFalse(db_update_result, "Database update with mismatched post_type must return False")

        # Verify DB content unchanged
        post_after = database.get_post_by_id(tour_id)
        self.assertEqual(post_after['message'], 'Original Tour Message')

    def test_02_cross_channel_delete_prevention(self):
        """
        Known Defect Resolution:
        A post created under 'tour' CANNOT be deleted through the 'nz' endpoint or
        with a mismatched post_type in database operations.
        """
        csrf = self._login()

        # 1. Create a post under 'tour'
        tour_id = database.add_post('tour', 'Protected Tour Post', 'tour_keep.png', organization_id=1)

        # 2. Attempt to delete tour_id through the 'nz' API route -> MUST FAIL (404)
        nz_del_res = self.client.delete(
            f'/api/posts/nz/{tour_id}',
            headers={'X-CSRFToken': csrf}
        )
        self.assertEqual(nz_del_res.status_code, 404, "Cross-channel delete must return 404 Not Found")

        # 3. Verify in database that tour post still exists
        self.assertIsNotNone(database.get_post_by_id(tour_id))

        # 4. Attempt direct database delete with mismatched post_type -> MUST return (None, False)
        img_fn, success = database.delete_post_by_id(tour_id, post_type='nz', organization_id=1)
        self.assertFalse(success, "Database delete with mismatched post_type must return False")
        self.assertIsNone(img_fn)

        # 5. Clean delete through correct channel 'tour' -> MUST succeed
        tour_del_res = self.client.delete(
            f'/api/posts/tour/{tour_id}',
            headers={'X-CSRFToken': csrf}
        )
        self.assertEqual(tour_del_res.status_code, 200)
        self.assertIsNone(database.get_post_by_id(tour_id))

    # =========================================================================
    # 2. MULTI-TENANCY & CROSS-ORGANIZATION RECORD ACCESS PREVENTION
    # =========================================================================

    def test_03_cross_organization_post_isolation(self):
        """
        Ensures strict tenant isolation:
        Posts belonging to Organization 1 cannot be seen, updated, or deleted by Organization 2.
        """
        # Create Organization 2
        org2_id = database.create_organization('Nexora Global Client', 'nexora-global', plan='starter')
        self.assertIsNotNone(org2_id)

        # Create post in Org 1 (GAATHA)
        p_org1 = database.add_post('gaatha', 'GAATHA Internal Strategy', None, organization_id=1)

        # Create post in Org 2
        p_org2 = database.add_post('gaatha', 'Org 2 Private Marketing', None, organization_id=org2_id)

        # 1. Scoped listings
        org1_posts = database.load_posts_by_type('gaatha', organization_id=1)
        org1_ids = [p['id'] for p in org1_posts]
        self.assertIn(p_org1, org1_ids)
        self.assertNotIn(p_org2, org1_ids, "Org 1 listing must NEVER leak Org 2 posts")

        org2_posts = database.load_posts_by_type('gaatha', organization_id=org2_id)
        org2_ids = [p['id'] for p in org2_posts]
        self.assertIn(p_org2, org2_ids)
        self.assertNotIn(p_org1, org2_ids, "Org 2 listing must NEVER leak Org 1 posts")

        # 2. Cross-org update attempt in DB
        cross_update = database.update_post_by_id(
            p_org1,
            message='Tampered by Org 2',
            post_type='gaatha',
            organization_id=org2_id
        )
        self.assertFalse(cross_update, "Cross-org post update must return False")

        # 3. Cross-org delete attempt in DB
        img_fn, cross_delete = database.delete_post_by_id(
            p_org1,
            post_type='gaatha',
            organization_id=org2_id
        )
        self.assertFalse(cross_delete, "Cross-org post deletion must return False")

        # 4. Search scoping
        org1_search = database.search_posts('Org 2 Private', organization_id=1)
        self.assertEqual(len(org1_search), 0, "Search scoped to Org 1 must not return Org 2 posts")

        org2_search = database.search_posts('Org 2 Private', organization_id=org2_id)
        self.assertEqual(len(org2_search), 1)

    # =========================================================================
    # 3. PRODUCTION SECRETS ENFORCEMENT & SECURITY CONFIGURATION
    # =========================================================================

    def test_04_production_secret_key_required(self):
        """
        Requirement 7:
        Ensure production secrets are explicitly configured rather than silently regenerated on process start.
        """
        import subprocess
        # Run a subprocess with APP_ENV=production, mock load_dotenv so it does not load local dev .env
        py_code = (
            "import os, sys\n"
            f"sys.path.insert(0, r'{REPO_ROOT}')\n"
            "os.environ['APP_ENV'] = 'production'\n"
            "os.environ.pop('SECRET_KEY', None)\n"
            "os.environ.pop('FLASK_SECRET_KEY', None)\n"
            "from unittest.mock import patch\n"
            "with patch('dotenv.load_dotenv'):\n"
            "    import config\n"
        )
        cmd = [sys.executable, "-c", py_code]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
        self.assertNotEqual(proc.returncode, 0, "config import must fail in production without explicit SECRET_KEY")
        self.assertIn("Production security configuration violation", proc.stderr)
        self.assertIn("SECRET_KEY must be explicitly configured", proc.stderr)

    def test_05_security_headers_and_path_traversal(self):
        """
        Requirement 8 & 13:
        Verifies defensive security headers on HTTP responses and path traversal rejection.
        """
        anon_client = application_module.app.test_client()
        res = anon_client.get('/login')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(res.headers.get('X-XSS-Protection'), '1; mode=block')
        self.assertEqual(res.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')

        # Path traversal check on media endpoint
        traversal_res = self.client.get('/images/../../etc/passwd')
        self.assertIn(traversal_res.status_code, (404, 400), "Path traversal must be neutralized")

    def test_06_token_leakage_prevention(self):
        """
        Requirement 9:
        Verifies tokens, secret keys, and password hashes are NEVER exposed in API outputs.
        """
        csrf = self._login()

        # Auth status
        me_res = self.client.get('/api/auth/me')
        self.assertEqual(me_res.status_code, 200)
        me_data = json.loads(me_res.data)
        self.assertNotIn('token', me_data)
        self.assertNotIn('access_token', me_data)
        self.assertNotIn('password', me_data)
        self.assertNotIn('password_hash', me_data)

        # Status endpoint
        status_res = self.client.get('/api/status')
        self.assertEqual(status_res.status_code, 200)
        status_text = status_res.data.decode('utf-8')
        self.assertNotIn('EAAT', status_text)
        self.assertNotIn('access_token', status_text)
        self.assertNotIn('Phase1_SecTest_Pass!', status_text)

    # =========================================================================
    # 4. PERSISTENT CALENDAR SCHEDULER & SAFE TASK LIFECYCLE
    # =========================================================================

    def test_07_persistent_calendar_scheduling_crud(self):
        """
        Verifies persistent scheduled post creation, retrieval, UTC normalization,
        updating, and cancellation.
        """
        csrf = self._login()

        # Target future schedule time in UTC
        target_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

        # 1. Create scheduled post via API
        create_res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': target_time,
                'message': 'Scheduled Launch Campaign Post',
                'image_filename': 'launch.png'
            },
            headers={'X-CSRFToken': csrf}
        )
        self.assertEqual(create_res.status_code, 201)
        sched_data = json.loads(create_res.data)
        sched_id = sched_data['id']
        self.assertEqual(sched_data['status'], 'scheduled')
        self.assertEqual(sched_data['post_type'], 'tour')
        self.assertIn('scheduled_for', sched_data)

        # 2. Retrieve scheduled posts list via API
        list_res = self.client.get('/api/schedule?post_type=tour')
        self.assertEqual(list_res.status_code, 200)
        items = json.loads(list_res.data)
        matched = [item for item in items if item['id'] == sched_id]
        self.assertEqual(len(matched), 1)

        # 3. Update scheduled post
        new_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        update_res = self.client.put(
            f'/api/schedule/{sched_id}',
            json={'message': 'Updated Campaign Message', 'scheduled_for': new_time},
            headers={'X-CSRFToken': csrf}
        )
        self.assertEqual(update_res.status_code, 200)

        # 4. Cancel scheduled post
        cancel_res = self.client.delete(f'/api/schedule/{sched_id}', headers={'X-CSRFToken': csrf})
        self.assertEqual(cancel_res.status_code, 200)

        # Verify status is 'cancelled'
        post = database.get_scheduled_post_by_id(sched_id)
        self.assertEqual(post['status'], 'cancelled')

    def test_08_multi_worker_atomic_claiming_and_duplicate_prevention(self):
        """
        Verifies that when two workers compete to claim the same due scheduled post,
        exactly ONE worker claims it atomically, preventing duplicate publishing.
        """
        # Create a post that is already due (scheduled in the past)
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        sp = database.create_scheduled_post(
            post_type='nz',
            scheduled_for=past_time,
            message='Due Post for Concurrency Testing',
            organization_id=1
        )
        sp_id = sp['id']

        claimed_worker_a = []
        claimed_worker_b = []

        def worker_a_claim():
            posts = database.claim_due_scheduled_posts("worker-proc-alpha", limit=5)
            for p in posts:
                if p['id'] == sp_id:
                    claimed_worker_a.append(p)

        def worker_b_claim():
            posts = database.claim_due_scheduled_posts("worker-proc-beta", limit=5)
            for p in posts:
                if p['id'] == sp_id:
                    claimed_worker_b.append(p)

        # Execute concurrent claims in separate threads
        t1 = threading.Thread(target=worker_a_claim)
        t2 = threading.Thread(target=worker_b_claim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly ONE worker claimed the post
        total_claims = len(claimed_worker_a) + len(claimed_worker_b)
        self.assertEqual(total_claims, 1, f"Expected exactly 1 claim, got {total_claims} (duplicate publishing risk!)")

        # The post is now locked in status 'publishing'
        post_state = database.get_scheduled_post_by_id(sp_id)
        self.assertEqual(post_state['status'], 'publishing')
        self.assertIn(post_state['locked_by'], ('worker-proc-alpha', 'worker-proc-beta'))

        # Complete publishing safely
        completed = database.complete_scheduled_post(sp_id, post_state['locked_by'], success=True)
        self.assertTrue(completed)
        self.assertEqual(database.get_scheduled_post_by_id(sp_id)['status'], 'published')

    def test_09_stale_worker_recovery(self):
        """
        Verifies crash recovery: If a worker crashed while publishing, an expired lock
        is safely recovered by a surviving worker.
        """
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        stale_lock_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).strftime("%Y-%m-%d %H:%M:%S")

        # Simulate crashed worker that locked a post 400 seconds ago
        sp = database.create_scheduled_post(
            post_type='tour',
            scheduled_for=past_time,
            message='Crashed Worker Post',
            organization_id=1
        )
        sp_id = sp['id']

        with database.get_db_connection() as conn:
            conn.execute(
                "UPDATE scheduled_posts SET status = 'publishing', locked_by = 'crashed-worker-999', locked_at = ? WHERE id = ?",
                (stale_lock_time, sp_id)
            )
            conn.commit()

        # Surviving worker claims due posts (with 300s timeout)
        recovered = database.claim_due_scheduled_posts("surviving-worker-001", limit=10, lock_timeout_seconds=300)
        rec_ids = [p['id'] for p in recovered]
        self.assertIn(sp_id, rec_ids, "Surviving worker must reclaim stale locked post from crashed worker")

        post_now = database.get_scheduled_post_by_id(sp_id)
        self.assertEqual(post_now['locked_by'], 'surviving-worker-001')

    def test_10_idempotency_duplicate_protection(self):
        """
        Verifies that scheduling requests with an existing idempotency_key
        return the existing post rather than creating duplicate jobs.
        """
        idem_key = "test-idempotency-key-uuid-98765"
        sp1 = database.create_scheduled_post(
            post_type='gaatha',
            scheduled_for="2026-11-04 10:00:00",
            message='Idempotent Post Attempt 1',
            idempotency_key=idem_key,
            organization_id=1
        )
        sp2 = database.create_scheduled_post(
            post_type='gaatha',
            scheduled_for="2026-11-04 10:00:00",
            message='Idempotent Post Attempt 2 (Duplicate)',
            idempotency_key=idem_key,
            organization_id=1
        )
        self.assertEqual(sp1['id'], sp2['id'], "Duplicate idempotency_key must return existing record")

    # =========================================================================
    # 5. INITIAL GAATHA WORKSPACES & DYNAMIC BRANDS SEEDING
    # =========================================================================

    def test_11_gaatha_initial_brand_workspaces(self):
        """
        Requirement 5.B:
        Verify initial GAATHA organization supports the six initial workspaces:
        1. GAATHA Suite
        2. GAATHA POS
        3. Sentira AI
        4. GAATHA Terra
        5. Phoenix — BY GAATHA
        6. GAATHA AI
        And supports dynamic creation of additional brands.
        """
        # Verify Organization 1 is GAATHA
        org1 = database.get_organization_by_id(1)
        self.assertIsNotNone(org1)
        self.assertEqual(org1['slug'], 'gaatha')

        # Verify the 6 initial brand workspaces
        brands = database.get_brands_by_organization(1)
        slugs = [b['slug'] for b in brands]

        expected_slugs = [
            'gaatha-suite',
            'gaatha-pos',
            'sentira-ai',
            'gaatha-terra',
            'phoenix-by-gaatha',
            'gaatha-ai'
        ]
        for es in expected_slugs:
            self.assertIn(es, slugs, f"Initial brand workspace '{es}' must be seeded")

        # Verify dynamic brand creation (not restricted to hardcoded six)
        new_brand_id = database.create_brand(1, 'GAATHA Cloud', 'gaatha-cloud', 'Cloud services marketing')
        self.assertIsNotNone(new_brand_id)
        updated_brands = database.get_brands_by_organization(1)
        self.assertIn('gaatha-cloud', [b['slug'] for b in updated_brands])

    def test_12_safe_non_destructive_schema_migration(self):
        """
        Requirement 15:
        Verify init_db() executes safely on existing tables without data corruption or loss.
        """
        # Create a post
        p_id = database.add_post('tour', 'Pre-Migration Post', 'pre.png', organization_id=1)
        self.assertIsNotNone(p_id)

        # Re-run init_db()
        database.init_db()

        # Confirm post still exists with all attributes intact
        p = database.get_post_by_id(p_id)
        self.assertIsNotNone(p)
        self.assertEqual(p['message'], 'Pre-Migration Post')
        self.assertEqual(p['organization_id'], 1)

    def test_13_role_authorization_viewer_read_only(self):
        """
        Unit M Security Hardening:
        Verify that users with 'viewer' role have strictly read-only access and cannot
        create, mutate, generate, or delete marketing campaigns, drafts, or media.
        """
        # Ensure session is viewer
        with self.client.session_transaction() as sess:
            sess['user_id'] = 999
            sess['username'] = 'test_viewer'
            sess['organization_id'] = 1
            sess['role'] = 'viewer'
            sess['csrf_token'] = 'csrf-test-token-viewer'

        headers = {'X-CSRFToken': 'csrf-test-token-viewer'}

        # Attempt to create campaign
        res = self.client.post('/api/campaigns', json={'brand_id': 1, 'name': 'Viewer Illegal Camp'}, headers=headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn('read-only', res.get_json().get('error', '').lower())

        # Attempt to update campaign
        res = self.client.put('/api/campaigns/1', json={'name': 'Viewer Update'}, headers=headers)
        self.assertEqual(res.status_code, 403)

        # Attempt to delete campaign
        res = self.client.delete('/api/campaigns/1', headers=headers)
        self.assertEqual(res.status_code, 403)

        # Attempt to generate copy
        res = self.client.post('/api/campaigns/1/generate', json={'platforms': ['facebook']}, headers=headers)
        self.assertEqual(res.status_code, 403)

        # Attempt to upload media
        res = self.client.post('/api/media/upload', data={'file': (io.BytesIO(b'dummy'), 'test.png')}, headers=headers)
        self.assertEqual(res.status_code, 403)

        # Attempt to delete media
        res = self.client.delete('/api/media/1', headers=headers)
        self.assertEqual(res.status_code, 403)

    def test_14_convert_all_plan_entries_to_drafts(self):
        """
        Unit M Reliability Hardening:
        Verify convert_all_plan_entries_to_drafts correctly translates all planned roadmap
        items into content drafts with revision 1 and tenant scoping.
        """
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'secadmin'
            sess['organization_id'] = 1
            sess['role'] = 'admin'
            sess['csrf_token'] = 'csrf-test-token-admin'

        headers = {'X-CSRFToken': 'csrf-test-token-admin'}

        # Create campaign and content plan directly in database
        brand_id = database.get_brands_by_organization(1)[0]['id']
        camp = database.create_campaign(1, brand_id, 'Plan Conversion Campaign', 'Awareness', 'Brief')
        plan = database.create_content_plan(1, brand_id, camp['id'], 'weekly', '2026-11-10', '2026-11-17', [
            {'day_number': 1, 'suggested_date': '2026-11-10', 'platform': 'facebook', 'topic': 'Brand launch post', 'headline': 'Hello World'},
            {'day_number': 2, 'suggested_date': '2026-11-11', 'platform': 'linkedin', 'topic': 'B2B Insight post', 'headline': 'Market Shift'}
        ])

        # Convert all to drafts via API
        res = self.client.post(f"/api/content-plans/{plan['id']}/convert-drafts", headers=headers)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data.get('drafts_count'), 2)
        self.assertEqual(len(data.get('drafts', [])), 2)

        # Verify revision 1 created on each
        for d in data['drafts']:
            self.assertEqual(d['current_revision'], 1)
            self.assertEqual(d['organization_id'], 1)

    def test_15_creative_validation_csrf_enforcement(self):
        """
        Unit M Security Hardening:
        Verify validate-creative endpoint requires CSRF protection on POST requests.
        """
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['role'] = 'admin'
            sess['csrf_token'] = 'valid-csrf-token'

        # POST without CSRF header must fail with 403
        res = self.client.post('/api/drafts/1/validate-creative')
        self.assertEqual(res.status_code, 403)

        # GET request without CSRF is allowed (safe read-only)
        res_get = self.client.get('/api/drafts/1/validate-creative')
        # Either 404 (draft 1 not found) or 200 (draft found), but NOT 403 CSRF rejected
        self.assertIn(res_get.status_code, [200, 404])


if __name__ == '__main__':
    unittest.main()
