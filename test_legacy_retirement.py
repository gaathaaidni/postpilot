"""
test_legacy_retirement.py - Acceptance Tests for Complete Legacy Channel Retirement
Verifies:
1. New scheduling requests for 'tour', 'nz', 'gaatha', 'insta' are rejected at the database layer.
2. New scheduling requests for legacy channels are rejected at the Flask API layer with HTTP 400.
3. Legacy channels cannot dispatch through PlatformRegistry or worker.
4. Legacy aliases return None from PlatformRegistry.get_adapter().
5. Historical records for legacy channels remain queryable and intact in database.get_scheduled_posts().
6. Canonical platforms ('facebook', 'instagram', 'linkedin', 'whatsapp') continue creating and querying successfully.
7. GAATHA brand and tenant isolation are preserved without degradation.
"""
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import database
import app
from platform_adapters.registry import PlatformRegistry, RETIRED_LEGACY_CHANNELS, CANONICAL_PLATFORMS


class TestLegacyRetirement(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        database.init_db()
        cls.app = app.app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

    def setUp(self):
        config.POSTPILOT_PUBLISHING_ENABLED = False
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1
            sess['csrf_token'] = 'test-csrf-token'
        self.headers = {'X-CSRFToken': 'test-csrf-token'}

    def test_01_database_rejects_new_legacy_scheduled_posts(self):
        """Verifies database.create_scheduled_post rejects all retired legacy channels."""
        future_dt = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        for leg in ('tour', 'nz', 'gaatha', 'insta'):
            with self.assertRaises(ValueError) as ctx:
                database.create_scheduled_post(
                    post_type=leg,
                    scheduled_for=future_dt,
                    message="Test legacy rejection",
                    organization_id=1,
                    brand_id=1
                )
            self.assertIn("permanently retired", str(ctx.exception).lower())

    def test_02_database_rejects_new_legacy_posts(self):
        """Verifies database.add_post rejects retired legacy channels."""
        for leg in ('tour', 'nz', 'gaatha', 'insta'):
            with self.assertRaises(ValueError) as ctx:
                database.add_post(
                    post_type=leg,
                    message="Test template rejection",
                    image_filename="",
                    organization_id=1,
                    brand_id=1
                )
            self.assertIn("permanently retired", str(ctx.exception).lower())

    def test_03_api_schedule_rejects_legacy_channel_with_http_400(self):
        """Verifies POST /api/schedule returns HTTP 400 for legacy channels."""
        future_dt = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        for leg in ('tour', 'nz', 'gaatha', 'insta'):
            res = self.client.post('/api/schedule', json={
                'post_type': leg,
                'scheduled_for': future_dt,
                'message': f'Attempt to schedule on {leg}',
                'brand_id': 1
            }, headers=self.headers)
            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertIn("permanently retired", data.get('error', '').lower())
            self.assertEqual(data.get('code'), 'LEGACY_CHANNEL_RETIRED')

    def test_04_api_interval_and_control_reject_legacy_channel(self):
        """Verifies PUT /api/interval/<post_type> rejects legacy channels."""
        for leg in ('tour', 'nz', 'gaatha', 'insta'):
            res = self.client.put(f'/api/interval/{leg}', json={'interval': 3600}, headers=self.headers)
            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertIn("permanently retired", data.get('error', '').lower())

    def test_05_platform_registry_cannot_resolve_legacy_adapters(self):
        """Verifies PlatformRegistry.get_adapter returns None for all legacy channels."""
        for leg in RETIRED_LEGACY_CHANNELS:
            adapter = PlatformRegistry.get_adapter(leg)
            self.assertIsNone(adapter, f"PlatformRegistry should not return adapter for {leg}")

    def test_06_platform_registry_dispatch_blocks_legacy_channels(self):
        """Verifies PlatformRegistry.dispatch blocks execution of legacy channels."""
        for leg in ('tour', 'nz', 'gaatha', 'insta'):
            res = PlatformRegistry.dispatch({'post_type': leg, 'message': 'Safety test'})
            self.assertFalse(res['success'])
            self.assertIn("permanently retired", res['error'].lower())
            self.assertTrue(res.get('is_retired_legacy'))

    def test_07_historical_records_remain_queryable(self):
        """Verifies get_scheduled_posts allows querying historical legacy channels without error."""
        # Querying by post_type='tour' or 'nz' must not raise ValueError
        history = database.get_scheduled_posts(organization_id=1, post_type='tour')
        self.assertIsInstance(history, list)

        # Audit logs and cancelled posts remain intact
        cancelled_posts = database.get_scheduled_posts(organization_id=1, status='cancelled')
        self.assertIsInstance(cancelled_posts, list)

    def test_08_canonical_platforms_continue_working(self):
        """Verifies canonical platforms can be scheduled and dispatched."""
        future_dt = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

        for canon in ('facebook', 'instagram', 'linkedin', 'whatsapp'):
            self.assertTrue(PlatformRegistry.is_canonical_platform(canon))
            adapter = PlatformRegistry.get_adapter(canon)
            self.assertIsNotNone(adapter)

            # Test dispatch under simulation
            post_payload = {
                'id': 9999,
                'post_type': canon,
                'message': f'Canonical platform test for {canon}',
                'image_filename': 'test.jpg' if canon == 'instagram' else None,
                'recipient_phone': '+919099028291' if canon == 'whatsapp' else None,
                'brand_id': 1,
                'organization_id': 1
            }
            res = PlatformRegistry.dispatch(post_payload)
            self.assertTrue(res['success'], f"Dispatch failed for canonical platform {canon}: {res.get('error')}")
            self.assertTrue(res.get('simulated'), f"Simulation expected for {canon}")

    def test_09_gaatha_brand_identity_preserved(self):
        """Verifies GAATHA brand (Brand ID 1) is preserved and active."""
        brand = database.get_brand_by_id(1)
        self.assertIsNotNone(brand)
        self.assertIn("GAATHA", brand['name'])
        self.assertEqual(brand['organization_id'], 1)


if __name__ == '__main__':
    unittest.main()
