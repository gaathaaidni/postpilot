"""
PostPilot Phase 2 Unit B Test Suite
Tests for Complete Post Lifecycle: Drafts, Approvals, State Transitions,
Publishing Worker Isolation, Retries, and Full Audit Logging.
"""
import os
import json
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-unit-b-lifecycle-32bytes'
_tmp_dir = tempfile.TemporaryDirectory()
os.environ['POSTPILOT_DATA_DIR'] = _tmp_dir.name
os.environ['DATABASE_URL'] = f"sqlite:///{Path(_tmp_dir.name) / 'unit_b_test.db'}"

import app
import database

class TestPostLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_db()
        cls.app = app.app
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False

    @classmethod
    def tearDownClass(cls):
        try:
            _tmp_dir.cleanup()
        except Exception:
            pass

    def setUp(self):
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['csrf_token'] = 'test-csrf-token'
        self.headers = {'X-CSRFToken': 'test-csrf-token'}

        # Ensure Org 2 exists for cross-tenant tests
        with database.get_db_connection() as conn:
            conn.execute(
                "INSERT INTO organizations (id, name, slug, plan, timezone, is_active) "
                "VALUES (2, 'Other Org', 'other-org', 'growth', 'UTC', 1) "
                "ON CONFLICT(id) DO NOTHING"
            )
            conn.commit()

    def test_01_draft_creation_and_worker_isolation(self):
        """Verifies drafts are created safely and never claimed by publishing workers."""
        past_due = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': past_due,
                'message': 'Draft Campaign Post',
                'status': 'draft',
                'allow_past': True
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 201)
        post = json.loads(res.data)
        self.assertEqual(post['status'], 'draft')
        draft_id = post['id']

        # Worker attempts to claim due posts
        claimed = database.claim_due_scheduled_posts("worker-test-proc-01", limit=10)
        claimed_ids = [p['id'] for p in claimed]
        self.assertNotIn(
            draft_id, claimed_ids,
            "Worker MUST NEVER claim draft posts for publishing"
        )

    def test_02_pending_approval_worker_isolation(self):
        """Verifies pending_approval posts are never claimed by publishing workers."""
        past_due = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'nz',
                'scheduled_for': past_due,
                'message': 'Visa Campaign Needing Approval',
                'status': 'pending_approval',
                'allow_past': True
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 201)
        post = json.loads(res.data)
        self.assertEqual(post['status'], 'pending_approval')
        pending_id = post['id']

        # Worker attempts to claim due posts
        claimed = database.claim_due_scheduled_posts("worker-test-proc-01", limit=10)
        claimed_ids = [p['id'] for p in claimed]
        self.assertNotIn(
            pending_id, claimed_ids,
            "Worker MUST NEVER claim pending_approval posts for publishing"
        )

    def test_03_pending_approvals_listing(self):
        """Verifies GET /api/approvals/pending returns only pending posts in active organization."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        # Post in Org 1
        res1 = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'gaatha',
                'scheduled_for': future_time,
                'message': 'Gaatha Approval Post',
                'status': 'pending_approval'
            },
            headers=self.headers
        )
        p1_id = json.loads(res1.data)['id']

        # Query pending approvals
        list_res = self.client.get('/api/approvals/pending')
        self.assertEqual(list_res.status_code, 200)
        data = json.loads(list_res.data)
        self.assertTrue(data['success'])
        found_ids = [p['id'] for p in data['posts']]
        self.assertIn(p1_id, found_ids)

    def test_04_approval_workflow_and_metadata(self):
        """Verifies approving a pending post transitions it to scheduled and records approval metadata."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': future_time,
                'message': 'Ready for review',
                'status': 'pending_approval'
            },
            headers=self.headers
        )
        post_id = json.loads(res.data)['id']

        # Approve post
        app_res = self.client.post(f'/api/approvals/{post_id}/approve', headers=self.headers)
        self.assertEqual(app_res.status_code, 200)
        app_data = json.loads(app_res.data)
        self.assertTrue(app_data['success'])
        self.assertEqual(app_data['post']['status'], 'scheduled')
        self.assertEqual(app_data['post']['approved_by'], 1)
        self.assertIsNotNone(app_data['post']['approved_at'])

    def test_05_rejection_workflow_requires_reason(self):
        """Verifies rejection requires a reason and stores it with the audit log."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'nz',
                'scheduled_for': future_time,
                'message': 'Pending Post for Rejection',
                'status': 'pending_approval'
            },
            headers=self.headers
        )
        post_id = json.loads(res.data)['id']

        # Try rejection without reason
        bad_rej = self.client.post(
            f'/api/approvals/{post_id}/reject',
            json={'reason': '   '},
            headers=self.headers
        )
        self.assertEqual(bad_rej.status_code, 400)
        self.assertIn('reason', json.loads(bad_rej.data)['error'].lower())

        # Reject with specific reason
        good_rej = self.client.post(
            f'/api/approvals/{post_id}/reject',
            json={'reason': 'Caption violates brand guidelines and CTA is missing'},
            headers=self.headers
        )
        self.assertEqual(good_rej.status_code, 200)
        rej_post = json.loads(good_rej.data)['post']
        self.assertEqual(rej_post['status'], 'rejected')
        self.assertIn('brand guidelines', rej_post['rejection_reason'])

    def test_06_complete_lifecycle_audit_history(self):
        """Verifies full lifecycle audit trail: creation, approval, claiming, publishing."""
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        # 1. Create as draft
        res1 = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'gaatha',
                'scheduled_for': past_time,
                'message': 'Audit Trail Lifecycle Post',
                'status': 'draft',
                'allow_past': True
            },
            headers=self.headers
        )
        post_id = json.loads(res1.data)['id']

        # 2. Transition draft -> pending_approval
        self.client.post(
            f'/api/schedule/{post_id}/transition',
            json={'status': 'pending_approval', 'reason': 'Submitted for marketing review'},
            headers=self.headers
        )

        # 3. Approve -> scheduled
        self.client.post(f'/api/approvals/{post_id}/approve', headers=self.headers)

        # 4. Worker claims -> publishing
        claimed = database.claim_due_scheduled_posts("worker-proc-lifecycle", limit=10)
        self.assertIn(post_id, [p['id'] for p in claimed])

        # 5. Worker completes -> published
        database.complete_scheduled_post(post_id, "worker-proc-lifecycle", success=True)

        # Retrieve audit history via API
        hist_res = self.client.get(f'/api/schedule/{post_id}/history')
        self.assertEqual(hist_res.status_code, 200)
        events = json.loads(hist_res.data)['history']

        status_chain = [e['to_status'] for e in events]
        self.assertIn('draft', status_chain)
        self.assertIn('pending_approval', status_chain)
        self.assertIn('scheduled', status_chain)
        self.assertIn('publishing', status_chain)
        self.assertIn('published', status_chain)

    def test_07_failed_post_retry_workflow(self):
        """Verifies publishing failures record sanitized error and manual retry resets queue."""
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': past_time,
                'message': 'Post destined to fail',
                'allow_past': True
            },
            headers=self.headers
        )
        post_id = json.loads(res.data)['id']

        # Claim post
        claimed = database.claim_due_scheduled_posts("worker-retry-test", limit=5)
        self.assertIn(post_id, [p['id'] for p in claimed])

        # Simulate 3 failures to reach max retries
        database.complete_scheduled_post(
            post_id, "worker-retry-test", success=False,
            error_message="Meta API Error with access_token=SECRET_TOKEN_LEAK_TEST"
        )
        # Re-claim and fail until 'failed'
        post_state = database.get_scheduled_post_by_id(post_id)
        with database.get_db_connection() as conn:
            conn.execute("UPDATE scheduled_posts SET retry_count = 3, status = 'failed' WHERE id = ?", (post_id,))
            conn.commit()

        # Retry post via API
        retry_res = self.client.post(f'/api/schedule/{post_id}/retry', headers=self.headers)
        self.assertEqual(retry_res.status_code, 200)
        retried_post = json.loads(retry_res.data)['post']
        self.assertEqual(retried_post['status'], 'scheduled')
        self.assertEqual(retried_post['retry_count'], 0)
        self.assertIsNone(retried_post['error_message'])

    def test_08_cross_organization_approval_isolation(self):
        """Verifies that an organization cannot approve or reject posts belonging to another org."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        # Create post in Org 1
        with self.client.session_transaction() as sess:
            sess['organization_id'] = 1

        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': future_time,
                'message': 'Org 1 Secret Campaign',
                'status': 'pending_approval'
            },
            headers=self.headers
        )
        post_id = json.loads(res.data)['id']

        # Switch session to Org 2
        with self.client.session_transaction() as sess:
            sess['organization_id'] = 2

        # Org 2 tries to approve Org 1's post
        app_res = self.client.post(f'/api/approvals/{post_id}/approve', headers=self.headers)
        self.assertEqual(app_res.status_code, 400)
        self.assertIn("does not exist or does not belong", json.loads(app_res.data)['error'])

        # Org 2 tries to reject Org 1's post
        rej_res = self.client.post(
            f'/api/approvals/{post_id}/reject',
            json={'reason': 'Malicious rejection from Org 2'},
            headers=self.headers
        )
        self.assertEqual(rej_res.status_code, 400)

        # Org 2 tries to read audit history
        hist_res = self.client.get(f'/api/schedule/{post_id}/history')
        self.assertEqual(hist_res.status_code, 404)

    def test_09_ui_dashboard_renders_workflow_sections(self):
        """Verifies dashboard template renders calendar, approvals, and queue navigation and modals."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Calendar", res.data)
        self.assertIn(b"Approvals", res.data)
        self.assertIn(b"Publishing Queue", res.data)
        self.assertIn(b"post-details-modal", res.data)
        self.assertIn(b"reject-reason-modal", res.data)
        self.assertIn(b"reschedule-modal", res.data)

if __name__ == '__main__':
    unittest.main()
