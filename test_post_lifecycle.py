"""
PostPilot Phase 2 Unit B Test Suite
Tests for Complete Post Lifecycle: Drafts, Approvals, State Transitions,
Publishing Worker Isolation, Retries, and Full Audit Logging.
"""
import os
import json
import unittest
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-unit-b-lifecycle-32bytes'
_tmp_dir = tempfile.TemporaryDirectory()
_lifecycle_db_path = Path(_tmp_dir.name) / 'unit_b_test.db'
_lifecycle_db_url = f"sqlite:///{_lifecycle_db_path}"

import config
import app
import database

class TestPostLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_config_db_url = getattr(config, 'DATABASE_URL', None)
        cls._orig_env_db_url = os.environ.get('DATABASE_URL')
        cls._orig_env_data_dir = os.environ.get('POSTPILOT_DATA_DIR')
        os.environ['POSTPILOT_DATA_DIR'] = _tmp_dir.name
        os.environ['DATABASE_URL'] = _lifecycle_db_url
        config.DATABASE_URL = _lifecycle_db_url
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
        if cls._orig_env_db_url:
            os.environ['DATABASE_URL'] = cls._orig_env_db_url
        else:
            os.environ.pop('DATABASE_URL', None)
        if cls._orig_env_data_dir:
            os.environ['POSTPILOT_DATA_DIR'] = cls._orig_env_data_dir
        else:
            os.environ.pop('POSTPILOT_DATA_DIR', None)
        if cls._orig_config_db_url:
            config.DATABASE_URL = cls._orig_config_db_url

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
                'post_type': 'facebook',
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
                'post_type': 'instagram',
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
                'post_type': 'linkedin',
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
                'post_type': 'facebook',
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
                'post_type': 'instagram',
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
                'post_type': 'linkedin',
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
                'post_type': 'facebook',
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
                'post_type': 'facebook',
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

    def test_10_invalid_initial_statuses_rejected_at_api_and_database(self):
        """
        Verifies that attempts to create posts directly as approved, publishing,
        published, failed, rejected, cancelled, or arbitrary statuses are rejected
        with HTTP 400 and code VALIDATION_ERROR, and zero records are inserted.
        """
        invalid_statuses = [
            'approved',
            'publishing',
            'published',
            'failed',
            'rejected',
            'cancelled',
            'random_unsupported_state',
            ''
        ]
        future_time = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

        # Count baseline posts
        with database.get_db_connection() as conn:
            initial_count = conn.execute("SELECT COUNT(*) as c FROM scheduled_posts").fetchone()['c']

        for inv_status in invalid_statuses:
            with self.subTest(invalid_status=inv_status):
                # 1. API level test
                res = self.client.post(
                    '/api/schedule',
                    json={
                        'post_type': 'facebook',
                        'scheduled_for': future_time,
                        'message': f'Post with illegal status {inv_status}',
                        'status': inv_status
                    },
                    headers=self.headers
                )
                self.assertEqual(
                    res.status_code, 400,
                    f"Creating post with initial status '{inv_status}' must return 400 Bad Request"
                )
                data = json.loads(res.data)
                self.assertEqual(data.get('code'), 'VALIDATION_ERROR')

                # 2. Database function level test
                with self.assertRaises(ValueError):
                    database.create_scheduled_post(
                        post_type='facebook',
                        scheduled_for=future_time,
                        message='Direct DB insertion illegal status',
                        initial_status=inv_status
                    )

        # Confirm no extra posts were inserted into database
        with database.get_db_connection() as conn:
            final_count = conn.execute("SELECT COUNT(*) as c FROM scheduled_posts").fetchone()['c']
        self.assertEqual(
            initial_count, final_count,
            "Database count must not increase after rejected invalid initial status attempts"
        )

    def test_11_contributor_role_cannot_schedule_directly(self):
        """Verifies that users with contributor role cannot schedule directly without approval."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with self.client.session_transaction() as sess:
            sess['role'] = 'contributor'

        # Attempt direct scheduling as contributor
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'instagram',
                'scheduled_for': future_time,
                'message': 'Contributor direct schedule attempt',
                'status': 'scheduled'
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(json.loads(res.data)['code'], 'APPROVAL_REQUIRED')

        # Contributor submitting as draft or pending_approval succeeds
        res_ok = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'instagram',
                'scheduled_for': future_time,
                'message': 'Contributor draft submission',
                'status': 'pending_approval'
            },
            headers=self.headers
        )
        self.assertEqual(res_ok.status_code, 201)
        self.assertEqual(json.loads(res_ok.data)['status'], 'pending_approval')

    def test_12_concurrent_conflicting_transitions_race_protection(self):
        """
        Verifies atomic state transitions under concurrent competing operations.
        Simultaneously attempts to approve and reject the same pending_approval post.
        Asserts exactly one transition succeeds, final status is valid, and audit log
        contains only the winning transition.
        """
        future_time = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'facebook',
                'scheduled_for': future_time,
                'message': 'Race Condition Test Post',
                'status': 'pending_approval'
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 201)
        post_id = json.loads(res.data)['id']

        results = []
        barrier = threading.Barrier(2)

        def worker_approve():
            barrier.wait()
            try:
                p = database.transition_post_status(
                    schedule_id=post_id,
                    to_status='scheduled',
                    user_id=1,
                    reason='Approved by Manager 1',
                    organization_id=1,
                    expected_from_status='pending_approval'
                )
                results.append(('approve', True, p))
            except Exception as e:
                results.append(('approve', False, str(e)))

        def worker_reject():
            barrier.wait()
            try:
                p = database.transition_post_status(
                    schedule_id=post_id,
                    to_status='rejected',
                    user_id=2,
                    reason='Rejected by Compliance Reviewer 2',
                    organization_id=1,
                    expected_from_status='pending_approval'
                )
                results.append(('reject', True, p))
            except Exception as e:
                results.append(('reject', False, str(e)))

        t1 = threading.Thread(target=worker_approve)
        t2 = threading.Thread(target=worker_reject)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one operation should succeed and one should fail
        successes = [r for r in results if r[1] is True]
        failures = [r for r in results if r[1] is False]

        self.assertEqual(len(successes), 1, f"Expected exactly 1 transition to succeed, got: {results}")
        self.assertEqual(len(failures), 1, f"Expected exactly 1 transition to fail, got: {results}")

        winner_action = successes[0][0]
        loser_error = failures[0][2]
        self.assertIn("Conflict", loser_error, "Failed operation must report a conflict error")

        # Verify final post status in database
        final_post = database.get_scheduled_post_by_id(post_id, organization_id=1)
        expected_status = 'scheduled' if winner_action == 'approve' else 'rejected'
        self.assertEqual(final_post['status'], expected_status)

        # Verify audit logs record only the winning transition
        history = database.get_post_audit_history(post_id, organization_id=1)
        transition_events = [e for e in history if e['from_status'] == 'pending_approval']
        self.assertEqual(len(transition_events), 1, "Only the winning transition should be recorded in audit log")
        self.assertEqual(transition_events[0]['to_status'], expected_status)

    def test_13_publishing_completion_tenant_channel_and_worker_isolation(self):
        """
        Verifies publishing completion enforces claim ownership, tenant isolation,
        and channel matching when updating last_posted_at on base posts.
        """
        with database.get_db_connection() as conn:
            # 1. Base post in Org 1, channel 'facebook'
            conn.execute(
                "INSERT INTO posts (id, post_type, message, organization_id, last_posted_at) "
                "VALUES (1001, 'facebook', 'Org 1 Tour Post', 1, NULL) "
                "ON CONFLICT(id) DO UPDATE SET last_posted_at = NULL"
            )
            # 2. Base post in Org 2, channel 'facebook'
            conn.execute(
                "INSERT INTO posts (id, post_type, message, organization_id, last_posted_at) "
                "VALUES (1002, 'facebook', 'Org 2 Tour Post', 2, NULL) "
                "ON CONFLICT(id) DO UPDATE SET last_posted_at = NULL"
            )
            # 3. Base post in Org 1, channel 'instagram'
            conn.execute(
                "INSERT INTO posts (id, post_type, message, organization_id, last_posted_at) "
                "VALUES (1003, 'instagram', 'Org 1 NZ Post', 1, NULL) "
                "ON CONFLICT(id) DO UPDATE SET last_posted_at = NULL"
            )
            conn.commit()

        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        # Schedule post in Org 1 referencing post 1001
        sched_rec = database.create_scheduled_post(
            post_type='facebook',
            scheduled_for=past_time,
            post_id=1001,
            organization_id=1,
            allow_past=True
        )
        sched_id = sched_rec['id']

        # Worker A claims the post
        claimed = database.claim_due_scheduled_posts("worker-proc-alpha", limit=5)
        self.assertIn(sched_id, [p['id'] for p in claimed])

        # Wrong worker attempts completion -> MUST BE REJECTED
        wrong_res = database.complete_scheduled_post(sched_id, "worker-proc-imposter", success=True)
        self.assertFalse(wrong_res, "Imposter worker must NOT be allowed to complete a post claimed by worker-proc-alpha")

        # Verify post 1001 last_posted_at is still NULL
        with database.get_db_connection() as conn:
            p1001 = conn.execute("SELECT last_posted_at FROM posts WHERE id = 1001").fetchone()
            self.assertIsNone(p1001['last_posted_at'])

        # Valid worker completes publishing successfully
        valid_res = database.complete_scheduled_post(sched_id, "worker-proc-alpha", success=True)
        self.assertTrue(valid_res)

        # Post 1001 (matching Org 1 and channel 'facebook') MUST have updated last_posted_at
        with database.get_db_connection() as conn:
            p1001 = conn.execute("SELECT last_posted_at FROM posts WHERE id = 1001").fetchone()
            self.assertIsNotNone(p1001['last_posted_at'])
            # Verify Org 2 post 1002 and Org 1 post 1003 remain untouched
            p1002 = conn.execute("SELECT last_posted_at FROM posts WHERE id = 1002").fetchone()
            self.assertIsNone(p1002['last_posted_at'], "Cross-tenant post must NEVER have last_posted_at updated")
            p1003 = conn.execute("SELECT last_posted_at FROM posts WHERE id = 1003").fetchone()
            self.assertIsNone(p1003['last_posted_at'], "Cross-channel post must NEVER have last_posted_at updated")

        # Calling complete again on already-published post returns False (claim already released)
        double_res = database.complete_scheduled_post(sched_id, "worker-proc-alpha", success=True)
        self.assertFalse(double_res)

if __name__ == '__main__':
    unittest.main()
