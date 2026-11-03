"""
PostPilot Phase 2 Unit A Test Suite
Tests for Scheduling API Validation, Timezone Normalization, Cross-Tenant Isolation,
Media Path Traversal Protection, and Idempotency.
"""
import os
import json
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Isolated temporary environment for tests
os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-unit-a-scheduler-validation-32bytes'
_tmp_dir = tempfile.TemporaryDirectory()
os.environ['POSTPILOT_DATA_DIR'] = _tmp_dir.name
os.environ['DATABASE_URL'] = f"sqlite:///{Path(_tmp_dir.name) / 'unit_a_test.db'}"

import app
import database
import timezone_utils

class TestSchedulerValidation(unittest.TestCase):
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
                "VALUES (2, 'External Corp', 'external-corp', 'growth', 'UTC', 1) "
                "ON CONFLICT(id) DO NOTHING"
            )
            # Add brand for Org 2
            conn.execute(
                "INSERT INTO brands (id, organization_id, name, slug, description, is_active) "
                "VALUES (201, 2, 'External Brand', 'external-brand', 'Org 2 Brand', 1) "
                "ON CONFLICT(id) DO NOTHING"
            )
            # Add brand for Org 1
            conn.execute(
                "INSERT INTO brands (id, organization_id, name, slug, description, is_active) "
                "VALUES (101, 1, 'GAATHA Flagship', 'gaatha-flagship', 'Org 1 Brand', 1) "
                "ON CONFLICT(id) DO NOTHING"
            )
            conn.commit()

    def test_01_timezones_api_endpoint(self):
        """Verifies GET /api/timezones returns organization default and supported zones."""
        res = self.client.get('/api/timezones')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertIn('timezones', data)
        self.assertIn('Asia/Kolkata', data['timezones'])
        self.assertIn('America/New_York', data['timezones'])
        self.assertIn('UTC', data['timezones'])
        self.assertEqual(data['default'], 'Asia/Kolkata')

    def test_02_invalid_timestamps_rejected(self):
        """Verifies malformed, ambiguous, and unparseable date/time strings return HTTP 400."""
        invalid_cases = [
            "not-a-date",
            "2026-13-45T99:99:99",
            "yesterday at 5pm",
            "",
            "   ",
            "2026-02-31T12:00:00"
        ]
        for bad_ts in invalid_cases:
            res = self.client.post(
                '/api/schedule',
                json={
                    'post_type': 'tour',
                    'scheduled_for': bad_ts,
                    'message': 'Testing bad timestamp'
                },
                headers=self.headers
            )
            self.assertEqual(
                res.status_code, 400,
                f"Expected HTTP 400 for bad timestamp '{bad_ts}', got {res.status_code}"
            )
            data = json.loads(res.data)
            self.assertIn('error', data)
            self.assertEqual(data.get('code'), 'VALIDATION_ERROR')

    def test_03_past_timestamps_rejected_by_default(self):
        """Verifies past scheduling times are strictly rejected unless explicitly allowed."""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': past_time,
                'message': 'Past scheduling attempt'
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn("past", data['error'].lower())

    def test_04_timezone_normalization_and_utc_conversion(self):
        """Verifies local times in specified timezones correctly convert to UTC in database."""
        # 2026-11-10 15:30:00 in Asia/Kolkata (UTC+05:30) is 10:00:00 UTC
        local_iso = "2026-11-10T15:30:00"
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'gaatha',
                'scheduled_for': local_iso,
                'timezone': 'Asia/Kolkata',
                'message': 'IST Post'
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 201)
        record = json.loads(res.data)
        self.assertEqual(record['scheduled_for'], '2026-11-10 10:00:00')
        self.assertEqual(record['timezone'], 'Asia/Kolkata')
        self.assertEqual(record['display_timezone'], 'Asia/Kolkata')
        self.assertIn('15:30:00', record['local_scheduled_for'])

    def test_05_daylight_saving_transitions(self):
        """Verifies Daylight Saving Time conversions for America/New_York (EDT vs EST)."""
        # Summer date (EDT = UTC-4): 12:00 EDT -> 16:00 UTC
        summer_time = "2027-07-15T12:00:00"
        res1 = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': summer_time,
                'timezone': 'America/New_York',
                'message': 'Summer EDT Post'
            },
            headers=self.headers
        )
        self.assertEqual(res1.status_code, 201)
        rec1 = json.loads(res1.data)
        self.assertEqual(rec1['scheduled_for'], '2027-07-15 16:00:00')

        # Winter date (EST = UTC-5): 12:00 EST -> 17:00 UTC
        winter_time = "2027-01-15T12:00:00"
        res2 = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': winter_time,
                'timezone': 'America/New_York',
                'message': 'Winter EST Post'
            },
            headers=self.headers
        )
        self.assertEqual(res2.status_code, 201)
        rec2 = json.loads(res2.data)
        self.assertEqual(rec2['scheduled_for'], '2027-01-15 17:00:00')

    def test_06_cross_organization_brand_rejection(self):
        """Verifies that referencing a brand belonging to another organization is rejected."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        # Brand 201 belongs to Organization 2, while current session is Org 1
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'nz',
                'scheduled_for': future_time,
                'brand_id': 201,
                'message': 'Cross Org Brand Attack'
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn("different organization", data['error'].lower())

    def test_07_cross_channel_post_reference_rejection(self):
        """Verifies that referencing a post from a different channel or organization is rejected."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        # Create a post for channel 'tour'
        post_id = database.add_post('tour', 'Base Tour Post', 'tour.jpg', organization_id=1)

        # Try to schedule referencing that post under channel 'nz' (cross-channel mismatch)
        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'nz',
                'scheduled_for': future_time,
                'post_id': post_id,
                'message': 'Cross Channel Collision Attempt'
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn("belongs to channel 'tour', not 'nz'", data['error'])

    def test_08_media_path_traversal_rejection(self):
        """Verifies malicious media filenames with path traversal or dangerous extensions are rejected."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        malicious_filenames = [
            "../../etc/passwd",
            "..\\..\\Windows\\System32\\cmd.exe",
            "/absolute/path/image.jpg",
            "evil_script.sh",
            "malware.exe",
            "image.jpg\0.exe"
        ]
        for bad_media in malicious_filenames:
            res = self.client.post(
                '/api/schedule',
                json={
                    'post_type': 'tour',
                    'scheduled_for': future_time,
                    'image_filename': bad_media,
                    'message': 'Path Traversal Media Test'
                },
                headers=self.headers
            )
            self.assertEqual(
                res.status_code, 400,
                f"Expected HTTP 400 for bad media '{bad_media}', got {res.status_code}"
            )

        # Valid filenames must be accepted
        res_ok = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': future_time,
                'image_filename': 'summer_campaign.jpg',
                'message': 'Valid Media Post'
            },
            headers=self.headers
        )
        self.assertEqual(res_ok.status_code, 201)

    def test_09_duplicate_idempotency_handling(self):
        """Verifies idempotency returns the exact existing record and prevents cross-org collisions."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        idem_key = "sched-unit-a-idem-key-445566"

        res1 = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'gaatha',
                'scheduled_for': future_time,
                'message': 'Idempotent Message 1',
                'idempotency_key': idem_key
            },
            headers=self.headers
        )
        self.assertEqual(res1.status_code, 201)
        id1 = json.loads(res1.data)['id']

        # Duplicate request with same idempotency key
        res2 = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'gaatha',
                'scheduled_for': future_time,
                'message': 'Idempotent Message 2',
                'idempotency_key': idem_key
            },
            headers=self.headers
        )
        self.assertEqual(res2.status_code, 201)
        id2 = json.loads(res2.data)['id']
        self.assertEqual(id1, id2, "Duplicate idempotency key must return existing post")

        # Now simulate Org 2 trying to use the same idempotency key (cross-org clash)
        with self.client.session_transaction() as sess:
            sess['organization_id'] = 2

        res_cross = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'gaatha',
                'scheduled_for': future_time,
                'message': 'Cross Org Idempotency Collision',
                'idempotency_key': idem_key
            },
            headers=self.headers
        )
        self.assertEqual(res_cross.status_code, 400)
        data = json.loads(res_cross.data)
        self.assertIn("collision across organizations", data['error'].lower())

    def test_10_unauthorized_post_update_and_cancellation(self):
        """Verifies that updating or cancelling another organization's post is denied."""
        future_time = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
        # Create post in Org 1
        with self.client.session_transaction() as sess:
            sess['organization_id'] = 1

        res = self.client.post(
            '/api/schedule',
            json={
                'post_type': 'tour',
                'scheduled_for': future_time,
                'message': 'Org 1 Post'
            },
            headers=self.headers
        )
        post_id = json.loads(res.data)['id']

        # Switch to Org 2
        with self.client.session_transaction() as sess:
            sess['organization_id'] = 2

        # Attempt to update Org 1's post as Org 2
        upd_res = self.client.put(
            f'/api/schedule/{post_id}',
            json={'message': 'Hacked Update'},
            headers=self.headers
        )
        self.assertEqual(upd_res.status_code, 404)

        # Attempt to cancel Org 1's post as Org 2
        del_res = self.client.delete(f'/api/schedule/{post_id}', headers=self.headers)
        self.assertEqual(del_res.status_code, 404)

        # Post in Org 1 remains untouched and scheduled
        p = database.get_scheduled_post_by_id(post_id, organization_id=1)
        self.assertEqual(p['status'], 'scheduled')
        self.assertEqual(p['message'], 'Org 1 Post')

    def test_11_calendar_date_range_and_timezone_queries(self):
        """Verifies calendar queries with start_date, end_date, and target timezone."""
        with self.client.session_transaction() as sess:
            sess['organization_id'] = 1

        t1 = "2027-05-01T10:00:00"
        t2 = "2027-05-15T10:00:00"
        t3 = "2027-06-01T10:00:00"

        for t in (t1, t2, t3):
            self.client.post(
                '/api/schedule',
                json={'post_type': 'tour', 'scheduled_for': t, 'timezone': 'UTC'},
                headers=self.headers
            )

        # Query range covering only May 2027
        res = self.client.get(
            '/api/schedule?start_date=2027-05-01T00:00:00&end_date=2027-05-31T23:59:59&timezone=America/New_York'
        )
        self.assertEqual(res.status_code, 200)
        items = json.loads(res.data)
        self.assertGreaterEqual(len(items), 2)
        for item in items:
            self.assertIn("2027-05", item['scheduled_for'])
            # Verify timezone localization was computed
            self.assertEqual(item['display_timezone'], 'America/New_York')
            self.assertIn('EDT', item['local_display'])

if __name__ == '__main__':
    unittest.main()
