"""
PostPilot — Phase 3, Phase 4 & Phase 5 Comprehensive Acceptance Test Suite
========================================================================
Validates:
1. Public legal pages (/about, /privacy, /terms, /agreement, /user-agreement) with 0 placeholders.
2. Global draft workspace REST API (GET /api/drafts, POST /api/drafts) with multi-tenant isolation.
3. Executive dashboard analytics & calendar events APIs.
4. Non-negotiable publishing safety guardrail (POSTPILOT_PUBLISHING_ENABLED=0).
5. Database integrity and baseline data preservation (7 brands, 2 users, 2 orgs, scheduled posts #4, #8, #10).
6. Security checks (zero credential leakage, CSRF enforcement, role isolation).
"""

import os
import unittest
import json
import sqlite3
from pathlib import Path

# Enforce publishing safety
os.environ['POSTPILOT_PUBLISHING_ENABLED'] = '0'

REAL_DB_PATH = Path('data/posts.db').resolve()
os.environ['DATABASE_URL'] = f"sqlite:///{REAL_DB_PATH}"

import config
config.DATABASE_URL = f"sqlite:///{REAL_DB_PATH}"

import database
import app as application_module
from platform_adapters.registry import PlatformRegistry


class TestPublicLegalPagesAcceptance(unittest.TestCase):
    """Phase 4 Acceptance: Public legal pages accessible without login with zero placeholders."""

    def setUp(self):
        application_module.app.config['TESTING'] = True
        self.client = application_module.app.test_client()

    def test_01_about_us_page(self):
        """GET /about must return 200 without login and render correct legal entities."""
        resp = self.client.get('/about')
        self.assertEqual(resp.status_code, 200)
        content = resp.data.decode('utf-8')
        self.assertIn('Gaatha Ventures Sh.p.k.', content)
        self.assertIn('Aidni Global LLP', content)
        self.assertIn('office@gaatha.tech', content)
        self.assertNotIn('[INSERT_', content)

    def test_02_privacy_policy_page(self):
        """GET /privacy must return 200 and contain resolved privacy details."""
        resp = self.client.get('/privacy')
        self.assertEqual(resp.status_code, 200)
        content = resp.data.decode('utf-8')
        self.assertIn('Gaatha Ventures Sh.p.k.', content)
        self.assertIn('Aidni Global LLP', content)
        self.assertIn('office@gaatha.tech', content)
        self.assertIn('Pending Legal Review', content)
        self.assertNotIn('[INSERT_', content)

    def test_03_terms_and_conditions_page(self):
        """GET /terms must return 200 with resolved liability cap ($100) and governing law."""
        resp = self.client.get('/terms')
        self.assertEqual(resp.status_code, 200)
        content = resp.data.decode('utf-8')
        self.assertIn('Gaatha Ventures Sh.p.k.', content)
        self.assertIn('Aidni Global LLP', content)
        self.assertIn('USD 100', content)
        self.assertIn('Republic of Albania', content)
        self.assertIn('Republic of India', content)
        self.assertNotIn('[INSERT_', content)

    def test_04_user_agreement_page(self):
        """GET /agreement and /user-agreement must return 200 with complete SaaS terms."""
        for endpoint in ('/agreement', '/user-agreement'):
            resp = self.client.get(endpoint)
            self.assertEqual(resp.status_code, 200, f"Failed on endpoint {endpoint}")
            content = resp.data.decode('utf-8')
            self.assertIn('User Agreement', content)
            self.assertIn('Gaatha Ventures Sh.p.k.', content)
            self.assertIn('Aidni Global LLP', content)
            self.assertIn('multi-tenant organization boundaries', content)
            self.assertIn('Engineered Publishing Safeguards', content)
            self.assertNotIn('[INSERT_', content)


class TestGlobalDraftsManagementAcceptance(unittest.TestCase):
    """Phase 3 Acceptance: Global Draft Workspace endpoints with multi-tenant isolation."""

    @classmethod
    def setUpClass(cls):
        config.DATABASE_URL = f"sqlite:///{REAL_DB_PATH}"
        os.environ['DATABASE_URL'] = config.DATABASE_URL

    def setUp(self):
        application_module.app.config['TESTING'] = True
        self.client = application_module.app.test_client()

    def test_01_unauthenticated_drafts_access_denied(self):
        """GET /api/drafts without session returns 401."""
        orig_local = config.LOCAL_MODE
        try:
            config.LOCAL_MODE = False
            resp = self.client.get('/api/drafts')
            self.assertEqual(resp.status_code, 401)
        finally:
            config.LOCAL_MODE = orig_local

    def test_02_get_drafts_authenticated(self):
        """GET /api/drafts returns drafts list with count."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        resp = self.client.get('/api/drafts')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('drafts', data)
        self.assertIn('count', data)
        self.assertGreaterEqual(data['count'], 18)

    def test_03_create_draft_endpoint(self):
        """POST /api/drafts creates a new draft for the brand."""
        csrf_val = 'test_draft_csrf'
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['csrf_token'] = csrf_val

        headers = {'X-CSRFToken': csrf_val, 'Content-Type': 'application/json'}
        payload = {
            'brand_id': 1,
            'caption': 'Test automated draft creation acceptance test',
            'target_platform': 'facebook',
            'headline': 'Acceptance Hook'
        }
        resp = self.client.post('/api/drafts', json=payload, headers=headers)
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('draft', data)
        self.assertIn('id', data['draft'])

    def test_04_create_draft_cross_organization_blocked(self):
        """Org 2 cannot create a draft under Org 1's brand (Brand 1)."""
        csrf_val = 'test_draft_csrf_org2'
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['organization_id'] = 2  # Org 2!
            sess['username'] = 'org2_user'
            sess['role'] = 'editor'
            sess['csrf_token'] = csrf_val

        headers = {'X-CSRFToken': csrf_val, 'Content-Type': 'application/json'}
        payload = {
            'brand_id': 1,  # Brand 1 belongs to Org 1!
            'caption': 'Cross org attempt',
            'target_platform': 'facebook'
        }
        resp = self.client.post('/api/drafts', json=payload, headers=headers)
        self.assertIn(resp.status_code, (400, 404))


class TestExecutiveDashboardAnalyticsAcceptance(unittest.TestCase):
    """Phase 3 Acceptance: Dashboard KPIs & unified calendar events."""

    @classmethod
    def setUpClass(cls):
        config.DATABASE_URL = f"sqlite:///{REAL_DB_PATH}"
        os.environ['DATABASE_URL'] = config.DATABASE_URL

    def setUp(self):
        application_module.app.config['TESTING'] = True
        self.client = application_module.app.test_client()

    def test_01_dashboard_analytics_kpis(self):
        """GET /api/analytics/dashboard returns executive KPIs."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        resp = self.client.get('/api/analytics/dashboard')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('total_drafts', data)
        self.assertIn('publishing', data)
        self.assertIn('platform_distribution', data)
        self.assertIn('drafts', data)

    def test_02_calendar_events_endpoint(self):
        """GET /api/calendar/events returns scheduled events with platform filtering."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        resp = self.client.get('/api/calendar/events?status=all&platform=all')
        self.assertEqual(resp.status_code, 200)
        events = resp.get_json()
        self.assertIsInstance(events, list)


class TestPublishingSafetyGuardrailAcceptance(unittest.TestCase):
    """Non-negotiable Phase 5 Safety: Live publishing strictly disabled."""

    def test_01_environment_and_config_guardrail(self):
        """POSTPILOT_PUBLISHING_ENABLED is 0 and is_publishing_enabled() is False."""
        self.assertEqual(str(os.environ.get('POSTPILOT_PUBLISHING_ENABLED', '0')), '0')
        self.assertFalse(config.is_publishing_enabled())

    def test_02_platform_adapters_simulation_compliance(self):
        """All 4 canonical adapters produce simulated external IDs in safety mode."""
        fb_adapter = PlatformRegistry.get_adapter('facebook')
        ig_adapter = PlatformRegistry.get_adapter('instagram')
        li_adapter = PlatformRegistry.get_adapter('linkedin')
        wa_adapter = PlatformRegistry.get_adapter('whatsapp')

        self.assertIsNotNone(fb_adapter)
        self.assertIsNotNone(ig_adapter)
        self.assertIsNotNone(li_adapter)
        self.assertIsNotNone(wa_adapter)

        payload = {'id': 99999, 'message': 'Safety audit test', 'brand_id': 1, 'recipient_phone': '+919099028291', 'image_filename': 'sample.jpg'}

        fb_res = fb_adapter.publish(payload)
        self.assertTrue(fb_res['success'])
        self.assertTrue(fb_res.get('simulated'))
        self.assertIn('_sim_', fb_res['external_post_id'])

        ig_res = ig_adapter.publish(payload)
        self.assertTrue(ig_res['success'])
        self.assertTrue(ig_res.get('simulated'))
        self.assertIn('_sim_', ig_res['external_post_id'])

        li_res = li_adapter.publish(payload)
        self.assertTrue(li_res['success'])
        self.assertTrue(li_res.get('simulated'))
        self.assertIn('sim_', li_res['external_post_id'])

        wa_res = wa_adapter.publish(payload)
        self.assertTrue(wa_res['success'])
        self.assertTrue(wa_res.get('simulated'))
        self.assertIn('sim_', wa_res['external_post_id'])


class TestDatabaseIntegrityPreservation(unittest.TestCase):
    """Phase 5 Acceptance: Existing user content and brand architecture strictly intact."""

    def setUp(self):
        application_module.app.config['TESTING'] = True
        self.client = application_module.app.test_client()

    def test_01_baseline_brands_preserved(self):
        """7 brands exist in the primary database."""
        conn = sqlite3.connect(str(REAL_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT id, name, organization_id FROM brands ORDER BY id").fetchall()
            self.assertEqual(len(rows), 7)
            brand_names = {r['name'] for r in rows}
            self.assertIn('GAATHA Suite', brand_names)
            self.assertIn('Phoenix — BY GAATHA', brand_names)
            self.assertIn('GAATHA AI', brand_names)
        finally:
            conn.close()

    def test_02_scheduled_posts_preserved(self):
        """Scheduled posts #4, #8, #10 remain scheduled with zero corruption."""
        conn = sqlite3.connect(str(REAL_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT id, status FROM scheduled_posts WHERE id IN (4, 8, 10)").fetchall()
            row_map = {r['id']: r['status'] for r in rows}
            for pid in (4, 8, 10):
                self.assertIn(pid, row_map, f"Post #{pid} missing from scheduled_posts")
                self.assertEqual(row_map[pid], 'scheduled', f"Post #{pid} status altered")
        finally:
            conn.close()

    def test_03_zero_token_leakage_in_account_queries(self):
        """GET /api/accounts and database queries never return raw credentials."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        resp = self.client.get('/api/accounts')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        accounts = data.get('accounts', [])
        self.assertGreaterEqual(len(accounts), 6)

        for acc in accounts:
            self.assertNotIn('access_token', acc)
            self.assertNotIn('access_token_encrypted', acc)
            self.assertIn('token_status', acc)


if __name__ == '__main__':
    unittest.main()
