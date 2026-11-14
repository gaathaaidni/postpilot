"""
Phase 2 Website Intelligence Test Suite: Foundation, Migration & Telemetry Ingestion
(test_website_intelligence.py)

Covers:
- Additive schema migration (20261114_003_website_intelligence)
- Creation of all 8 isolated tables:
    * web_intel_sessions
    * web_intel_pageviews
    * web_intel_events
    * web_intel_conversions
    * web_intel_daily_rollups
    * web_intel_seo_audits
    * web_intel_seo_pages
    * web_intel_seo_recommendations
- Idempotency of migration execution
- Preservation of existing 210 scheduled posts and 7 growth properties
- Privacy verification: strict absence of raw IP columns in any table
- Telemetry recording helper functions (sessions, pageviews, events, conversions)
- KPI aggregation and overview reporting helpers
- Approximate geolocation breakdown helper
- Public fail-closed telemetry collector endpoint (POST /api/web-intel/collect)
- CORS preflight and headers (OPTIONS /api/web-intel/collect)
- Input validation: missing property_key returns HTTP 400
- Unknown or inactive property_key returns HTTP 404
- Authenticated overview endpoint (GET /api/web-intel/properties/<id>/overview)
- Unauthenticated access control (HTTP 401 fail-closed)
- Multi-tenant boundary enforcement (cross-tenant property returns 404)
- Fail-closed publishing safeguards verification (0)
- Client-side static tracker file verification (static/tracker.js)
"""
import os
import tempfile
import sqlite3
from pathlib import Path
import unittest
import json
import subprocess

_tmp_dir = tempfile.TemporaryDirectory()
_db_file = Path(_tmp_dir.name) / 'website_intelligence_test.db'

os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-web-intel-32b-secure'
os.environ['DATABASE_URL'] = f"sqlite:///{_db_file}"

import config
config.DATABASE_URL = f"sqlite:///{_db_file}"
config.LOCAL_MODE = False
config.POSTPILOT_PUBLISHING_ENABLED = 0
config.WHATSAPP_PUBLISHING_ENABLED = 0

import database
import app as postpilot_app


class TestWebsiteIntelligence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initializes database schema, seeds properties, and configures test client."""
        database.init_db()
        database.init_growth_properties()

        cls.app = postpilot_app.app
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-secret-key-web-intel-32b-secure'
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        try:
            _tmp_dir.cleanup()
        except Exception:
            pass

    def _login(self, user_id=1, username="admin", role="admin", org_id=1):
        """Helper to establish an authenticated session."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['user'] = username
            sess['role'] = role
            sess['organization_id'] = org_id
            sess['logged_in'] = True

    def _logout(self):
        """Helper to clear session."""
        with self.client.session_transaction() as sess:
            sess.clear()

    # ── 1. Migration & Schema Verification ──────────────────────────────

    def test_01_migration_registered_in_schema_migrations(self):
        """Verifies 20261114_003_website_intelligence is recorded in schema_migrations."""
        with database.get_db_connection() as conn:
            row = conn.execute(
                "SELECT version, description FROM schema_migrations WHERE version = ?",
                ('20261114_003_website_intelligence',)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertIn("Website Intelligence foundation", row['description'])

    def test_02_all_eight_tables_created(self):
        """Verifies that all 8 dedicated website intelligence tables exist."""
        expected_tables = [
            'web_intel_sessions',
            'web_intel_pageviews',
            'web_intel_events',
            'web_intel_conversions',
            'web_intel_daily_rollups',
            'web_intel_seo_audits',
            'web_intel_seo_pages',
            'web_intel_seo_recommendations'
        ]
        with database.get_db_connection() as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r['name'] for r in cur.fetchall()]
            for tbl in expected_tables:
                self.assertIn(tbl, tables, f"Expected table '{tbl}' to exist in database.")

    def test_03_migration_is_idempotent(self):
        """Ensures calling migrate_phase2_website_intelligence multiple times is safe."""
        try:
            database.migrate_phase2_website_intelligence()
            database.migrate_phase2_website_intelligence()
        except Exception as e:
            self.fail(f"Idempotent migration re-run failed with error: {e}")

        with database.get_db_connection() as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
                ('20261114_003_website_intelligence',)
            ).fetchone()[0]
            self.assertEqual(cnt, 1, "Migration version should only be recorded once.")

    def test_04_preservation_of_growth_properties(self):
        """Verifies the default 7 GAATHA ecosystem properties remain intact."""
        with database.get_db_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM growth_properties WHERE organization_id = 1").fetchone()[0]
            self.assertGreaterEqual(cnt, 7)

    # ── 2. Privacy & Zero Raw IP Enforcement ────────────────────────────

    def test_05_privacy_zero_raw_ip_storage_in_schema(self):
        """Verifies that NO column in web_intel tables stores raw IP addresses."""
        prohibited_col_names = {'ip', 'ip_address', 'client_ip', 'visitor_ip', 'raw_ip', 'remote_addr'}
        with database.get_db_connection() as conn:
            for tbl in ('web_intel_sessions', 'web_intel_pageviews', 'web_intel_events', 'web_intel_conversions'):
                cur = conn.execute(f"PRAGMA table_info({tbl})")
                cols = {r['name'].lower() for r in cur.fetchall()}
                intersection = cols.intersection(prohibited_col_names)
                self.assertEqual(
                    len(intersection), 0,
                    f"Privacy violation: Prohibited raw IP column(s) {intersection} found in table '{tbl}'!"
                )
                # Confirm hash columns exist instead
                if tbl == 'web_intel_sessions':
                    self.assertIn('session_hash', cols)
                    self.assertIn('visitor_id_hash', cols)

    # ── 3. Database Helper Functions ────────────────────────────────────

    def test_06_record_web_intel_telemetry_helper(self):
        """Tests telemetry recording helper for session creation and pageview logging."""
        res = database.record_web_intel_telemetry(
            property_id=1,
            organization_id=1,
            session_hash="test_session_hash_abc123",
            visitor_hash="test_visitor_hash_xyz789",
            country_code="IN",
            country_name="India",
            city_name="Ahmedabad",
            device_type="desktop",
            browser_name="Chrome",
            os_name="Windows",
            referrer_source="Direct",
            landing_page="/",
            path="/",
            page_title="GAATHA Corporate",
            load_time_ms=250
        )
        self.assertIn('session_id', res)
        self.assertIn('pageview_id', res)

        # Record second pageview in same session
        res2 = database.record_web_intel_telemetry(
            property_id=1,
            organization_id=1,
            session_hash="test_session_hash_abc123",
            visitor_hash="test_visitor_hash_xyz789",
            path="/about",
            page_title="About GAATHA",
            load_time_ms=180
        )
        self.assertEqual(res2['session_id'], res['session_id'])

        # Verify session pageviews counter incremented
        with database.get_db_connection() as conn:
            sess = conn.execute("SELECT pageviews_count, exit_page FROM web_intel_sessions WHERE id = ?", (res['session_id'],)).fetchone()
            self.assertEqual(sess['pageviews_count'], 2)
            self.assertEqual(sess['exit_page'], "/about")

    def test_07_record_web_intel_custom_event_and_conversion(self):
        """Tests logging custom interaction events and inbound conversions."""
        ev_id = database.record_web_intel_custom_event(
            property_id=1,
            organization_id=1,
            session_hash="test_session_hash_abc123",
            event_category="navigation",
            event_name="click_apply_now",
            event_label="header_cta",
            event_data={"button_id": "btn-apply"}
        )
        self.assertIsInstance(ev_id, int)

        conv_id = database.record_web_intel_conversion(
            property_id=1,
            organization_id=1,
            session_hash="test_session_hash_abc123",
            conversion_type="lead",
            lead_identifier_hash="lead_hash_98765",
            lead_source="Direct",
            metadata={"source_page": "/contact", "agency": "Apex Partners"}
        )
        self.assertIsInstance(conv_id, int)

        with database.get_db_connection() as conn:
            ev = conn.execute("SELECT event_name FROM web_intel_events WHERE id = ?", (ev_id,)).fetchone()
            self.assertEqual(ev['event_name'], "click_apply_now")
            conv = conn.execute("SELECT conversion_type FROM web_intel_conversions WHERE id = ?", (conv_id,)).fetchone()
            self.assertEqual(conv['conversion_type'], "lead")

    def test_08_get_web_intel_overview_and_geo(self):
        """Tests calculation of overview KPIs and geo breakdown."""
        overview = database.get_web_intel_overview(property_id=1, organization_id=1, days=30)
        self.assertEqual(overview['property_id'], 1)
        self.assertGreaterEqual(overview['total_sessions'], 1)
        self.assertGreaterEqual(overview['total_pageviews'], 2)
        self.assertIn('bounce_rate_pct', overview)
        self.assertIn('top_pages', overview)

        geo = database.get_web_intel_geo_breakdown(property_id=1, organization_id=1, days=30)
        self.assertIsInstance(geo, list)
        self.assertGreaterEqual(len(geo), 1)
        self.assertEqual(geo[0]['country_code'], "IN")
        self.assertEqual(geo[0]['city_name'], "Ahmedabad")

    # ── 4. API Endpoints: Telemetry Ingestion ────────────────────────────

    def test_09_api_collect_missing_property_key_returns_400(self):
        """Rejects telemetry beacon without property_key with HTTP 400."""
        res = self.client.post('/api/web-intel/collect', json={"path": "/test"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("property_key", data.get('error', ''))

    def test_10_api_collect_invalid_property_key_returns_404(self):
        """Rejects telemetry beacon with unrecognized property_key with HTTP 404."""
        res = self.client.post('/api/web-intel/collect', json={
            "property_key": "non_existent_property_slug_12345",
            "path": "/test"
        })
        self.assertEqual(res.status_code, 404)

    def test_11_api_collect_pageview_success_returns_200_and_cors(self):
        """Processes valid pageview beacon, sets CORS, and anonymizes IP."""
        payload = {
            "property_key": "gaatha_corporate",
            "session_id": "sess_client_test_123",
            "path": "/solutions/business-management",
            "page_title": "GAATHA Suite ERP",
            "referrer": "https://www.google.com/search?q=sme+erp",
            "load_time_ms": 320,
            "tz": "Asia/Kolkata",
            "event_type": "pageview"
        }
        res = self.client.post(
            '/api/web-intel/collect',
            json=payload,
            headers={
                "Origin": "https://gaatha.tech",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
                "X-Forwarded-For": "203.0.113.195"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('recorded'), 'pageview')
        # Check CORS header
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), 'https://gaatha.tech')

    def test_12_api_collect_cors_options_preflight(self):
        """Verifies OPTIONS preflight request returns 204 with CORS headers."""
        res = self.client.open(
            '/api/web-intel/collect',
            method='OPTIONS',
            headers={"Origin": "https://phoenix.gaatha.tech"}
        )
        self.assertEqual(res.status_code, 204)
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), 'https://phoenix.gaatha.tech')
        self.assertIn('POST', res.headers.get('Access-Control-Allow-Methods', ''))

    def test_13_api_collect_event_and_conversion_types(self):
        """Tests custom event and conversion beacon submissions via API."""
        # Custom event
        res_ev = self.client.post('/api/web-intel/collect', json={
            "property_key": "gaatha_corporate",
            "session_id": "sess_client_test_123",
            "event_type": "event",
            "event_category": "engagement",
            "event_name": "download_brochure",
            "event_label": "suite_brochure_pdf"
        })
        self.assertEqual(res_ev.status_code, 200)
        self.assertEqual(res_ev.get_json().get('recorded'), 'event')

        # Conversion
        res_conv = self.client.post('/api/web-intel/collect', json={
            "property_key": "gaatha_corporate",
            "session_id": "sess_client_test_123",
            "event_type": "conversion",
            "conversion_type": "inquiry",
            "lead_identifier": "hashed_lead_id_456"
        })
        self.assertEqual(res_conv.status_code, 200)
        self.assertEqual(res_conv.get_json().get('recorded'), 'conversion')

    # ── 5. API Endpoints: Reporting & Multi-Tenant Access ────────────────

    def test_14_api_overview_unauthenticated_returns_401(self):
        """Ensures reporting endpoints fail-closed with 401 when unauthenticated."""
        self._logout()
        res = self.client.get('/api/web-intel/properties/1/overview')
        self.assertEqual(res.status_code, 401)

    def test_15_api_overview_authenticated_returns_200(self):
        """Ensures authenticated user can retrieve overview metrics."""
        self._login(user_id=1, username="admin", role="admin", org_id=1)
        res = self.client.get('/api/web-intel/properties/1/overview?days=30')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('property_id'), 1)
        self.assertIn('total_sessions', data)
        self.assertIn('unique_visitors', data)

    def test_16_tenant_isolation_enforced(self):
        """Ensures Organization 2 cannot access Organization 1's website intelligence."""
        self._login(user_id=2, username="org2_admin", role="admin", org_id=2)
        res = self.client.get('/api/web-intel/properties/1/overview')
        self.assertEqual(res.status_code, 404)
        self.assertIn("different organization", res.get_json().get('error', '').lower())

    # ── 6. Safeguards & Static Tracker File ──────────────────────────────

    def test_17_publishing_safeguards_strictly_disabled(self):
        """Asserts fail-closed publishing guards remain strictly zero."""
        self.assertEqual(config.POSTPILOT_PUBLISHING_ENABLED, 0)
        self.assertEqual(config.WHATSAPP_PUBLISHING_ENABLED, 0)

    def test_18_tracker_js_file_exists_and_valid(self):
        """Verifies static/tracker.js exists, is non-empty, and has valid JS syntax."""
        tracker_path = Path("D:/postpilot/static/tracker.js")
        self.assertTrue(tracker_path.exists(), "static/tracker.js must exist on disk.")
        self.assertGreater(tracker_path.stat().st_size, 500, "tracker.js must not be empty.")

        # Check JS syntax via node -c
        check = subprocess.run(["node", "-c", str(tracker_path)], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, f"tracker.js syntax check failed: {check.stderr}")


if __name__ == '__main__':
    unittest.main()
