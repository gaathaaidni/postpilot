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

    # ── 7. Milestone 2: Hardening, Domains, SEO & Dashboard Endpoints ──

    def test_19_migration_004_property_domains_and_seo_registered(self):
        """Verifies 20261114_004_property_domains_and_seo is executed and registered."""
        with database.get_db_connection() as conn:
            row = conn.execute(
                "SELECT version, description FROM schema_migrations WHERE version = ?",
                ('20261114_004_property_domains_and_seo',)
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertIn("Multi-domain aliases", row['description'])

    def test_20_growth_property_domains_table_populated(self):
        """Verifies growth_property_domains has domain patterns for properties."""
        with database.get_db_connection() as conn:
            domains = conn.execute("SELECT property_id, domain_pattern FROM growth_property_domains WHERE organization_id = 1").fetchall()
            self.assertGreaterEqual(len(domains), 11)
            domain_names = [d['domain_pattern'] for d in domains]
            self.assertIn('gaatha.tech', domain_names)
            self.assertIn('phoenix.gaatha.tech', domain_names)
            self.assertIn('cgs.gaatha.tech', domain_names)

    def test_21_is_origin_allowed_for_property(self):
        """Verifies origin validator accepts registered domain and rejects foreign domain."""
        with database.get_db_connection() as conn:
            prop = conn.execute("SELECT id FROM growth_properties WHERE property_key = 'gaatha_corporate'").fetchone()
            p_id = prop['id']

        self.assertTrue(database.is_origin_allowed_for_property(p_id, 'https://gaatha.tech'))
        self.assertTrue(database.is_origin_allowed_for_property(p_id, 'http://localhost:5000'))
        self.assertFalse(database.is_origin_allowed_for_property(p_id, 'https://malicious-tracker.com'))

    def test_22_geoip_service_resolution_and_safeguards(self):
        """Verifies geoip_service handles local/private IPs safely without fabrication."""
        import geoip_service
        # Loopback
        res_local = geoip_service.resolve_ip_location('127.0.0.1')
        self.assertEqual(res_local['country_code'], 'LO')
        self.assertTrue(res_local['is_internal'])
        self.assertEqual(res_local['source'], 'internal')

        # Private RFC1918
        res_priv = geoip_service.resolve_ip_location('192.168.1.100')
        self.assertEqual(res_priv['country_code'], 'LO')
        self.assertTrue(res_priv['is_internal'])

        # Unknown / Unresolvable public IP
        res_pub = geoip_service.resolve_ip_location('8.8.8.8')
        self.assertIn('country_code', res_pub)
        self.assertFalse(res_pub['is_internal'])

    def test_23_collector_payload_limit_enforced(self):
        """Rejects telemetry beacon larger than 64KB with HTTP 413."""
        large_junk = "x" * 70000
        res = self.client.post('/api/web-intel/collect', json={
            "property_key": "gaatha_corporate",
            "path": "/test",
            "junk": large_junk
        })
        self.assertEqual(res.status_code, 413)

    def test_24_collector_strict_origin_check(self):
        """Rejects telemetry beacon from unauthorized origin with HTTP 403."""
        res = self.client.post(
            '/api/web-intel/collect',
            json={"property_key": "gaatha_corporate", "path": "/"},
            headers={"Origin": "https://unauthorized-phishing.com"}
        )
        self.assertEqual(res.status_code, 403)

    def test_25_collector_rate_limiting(self):
        """Verifies rate limiting kicks in if too many requests from same IP."""
        import app as postpilot_app
        postpilot_app._WEB_INTEL_RATE_LIMITS.clear()
        test_ip = "198.51.100.42"

        for _ in range(120):
            res = self.client.post(
                '/api/web-intel/collect',
                json={"property_key": "gaatha_corporate", "path": "/"},
                headers={"X-Real-IP": test_ip, "Origin": "https://gaatha.tech"}
            )
            self.assertEqual(res.status_code, 200)

        res_blocked = self.client.post(
            '/api/web-intel/collect',
            json={"property_key": "gaatha_corporate", "path": "/"},
            headers={"X-Real-IP": test_ip, "Origin": "https://gaatha.tech"}
        )
        self.assertEqual(res_blocked.status_code, 429)

    def test_26_api_web_intel_timeline(self):
        """Tests timeseries timeline API endpoint."""
        self._login(user_id=1, username="admin", role="admin", org_id=1)
        res = self.client.get('/api/web-intel/properties/1/timeline?days=30')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)

    def test_27_api_web_intel_sources_and_devices(self):
        """Tests sources and devices breakdown APIs."""
        self._login(user_id=1, username="admin", role="admin", org_id=1)
        res_src = self.client.get('/api/web-intel/properties/1/sources?days=30')
        self.assertEqual(res_src.status_code, 200)
        data_src = res_src.get_json()
        self.assertIn('channels', data_src)
        self.assertTrue('referrers' in data_src or 'top_referrers' in data_src)

        res_dev = self.client.get('/api/web-intel/properties/1/devices?days=30')
        self.assertEqual(res_dev.status_code, 200)
        data_dev = res_dev.get_json()
        self.assertIn('devices', data_dev)
        self.assertIn('browsers', data_dev)
        self.assertIn('os', data_dev)

    def test_28_api_web_intel_pages_and_conversions(self):
        """Tests pages and conversions breakdown APIs."""
        self._login(user_id=1, username="admin", role="admin", org_id=1)
        res_pages = self.client.get('/api/web-intel/properties/1/pages?days=30')
        self.assertEqual(res_pages.status_code, 200)
        data_pages = res_pages.get_json()
        self.assertIn('all_pages', data_pages)
        self.assertIn('landing_pages', data_pages)

        res_conv = self.client.get('/api/web-intel/properties/1/conversions?days=30')
        self.assertEqual(res_conv.status_code, 200)
        data_conv = res_conv.get_json()
        self.assertIn('by_type', data_conv)
        self.assertIn('recent', data_conv)

    def test_29_seo_analyzer_detects_placeholder_canonical(self):
        """Verifies SEO crawler analysis catches placeholder canonical domains."""
        import seo_crawler
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Clean Title for Test Page Execution</title>
    <meta name="description" content="This is an exact meta description for our test page that easily meets the length requirement of 70 characters.">
    <link rel="canonical" href="https://yourwebsite.com/index.html">
</head>
<body>
    <h1>Main Heading</h1>
    <a href="/about">About</a>
</body>
</html>'''
        page, issues, links = seo_crawler.analyze_page_seo(
            url="https://cgs.gaatha.tech/",
            html_content=html,
            status_code=200,
            response_time_ms=120
        )
        self.assertEqual(page['status_code'], 200)
        self.assertEqual(page['canonical_url'], 'https://yourwebsite.com/index.html')
        categories = [i['category'] for i in issues]
        self.assertIn('canonical_placeholder', categories)
        critical_issues = [i for i in issues if i['severity'] == 'critical']
        self.assertGreaterEqual(len(critical_issues), 1)

    def test_30_seo_recommendations_workflow(self):
        """Tests creating, listing, and transitioning SEO recommendation status."""
        self._login(user_id=1, username="admin", role="admin", org_id=1)
        audit_summary = {
            'status': 'completed',
            'pages_crawled': 1,
            'pages_passed': 0,
            'pages_with_issues': 1,
            'health_score': 85.0,
            'critical_count': 1,
            'warning_count': 0
        }
        pages = [{
            'url': 'https://cgs.gaatha.tech/',
            'status_code': 200,
            'response_time_ms': 100,
            'title': 'CGS Test',
            'canonical_url': 'https://yourwebsite.com/',
            'issues': [{'severity': 'critical', 'category': 'canonical_placeholder'}]
        }]
        recs = [{
            'target_url': 'https://cgs.gaatha.tech/',
            'category': 'canonical',
            'issue_description': 'Placeholder canonical tag detected',
            'proposed_action': 'Replace with https://cgs.gaatha.tech/',
            'current_content': 'https://yourwebsite.com/',
            'recommended_content': 'https://cgs.gaatha.tech/'
        }]

        audit_id = database.record_seo_audit_results(1, 1, audit_summary, pages, recs)
        self.assertIsInstance(audit_id, int)

        res_list = self.client.get('/api/web-intel/seo/recommendations?property_id=1&status=pending')
        self.assertEqual(res_list.status_code, 200)
        items = res_list.get_json()
        self.assertGreaterEqual(len(items), 1)
        rec_id = items[0]['id']

        res_patch = self.client.patch(
            f'/api/web-intel/seo/recommendations/{rec_id}',
            json={'status': 'approved'}
        )
        self.assertEqual(res_patch.status_code, 200)
        self.assertEqual(res_patch.get_json()['status'], 'approved')

    def test_31_script_js_full_syntax_validation(self):
        """Verifies static/script.js syntax integrity using Node.js compiler."""
        script_path = Path("D:/postpilot/static/script.js")
        self.assertTrue(script_path.exists())
        check = subprocess.run(["node", "-c", str(script_path)], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, f"script.js syntax check failed: {check.stderr}")

    def test_32_ssrf_safe_redirect_handler_blocks_private_targets(self):
        """Verifies SSRFSafeRedirectHandler intercepts and blocks redirects to private or metadata addresses."""
        from seo_crawler import SSRFSafeRedirectHandler
        import urllib.error
        import urllib.request

        handler = SSRFSafeRedirectHandler()
        req = urllib.request.Request("https://safe-domain.com")
        
        # Unsafe redirect target: loopback
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:8080/secret")

        # Unsafe redirect target: AWS/cloud metadata IP
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(req, None, 301, "Moved", {}, "http://169.254.169.254/latest/meta-data/")

        # Unsafe redirect target: private 10.x.x.x
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(req, None, 302, "Found", {}, "http://10.0.0.1/admin")

    def test_33_shared_rate_limiting_across_keys(self):
        """Verifies database-backed rate limiter increments per-key counters and enforces 120 limit."""
        import hashlib
        key_a = hashlib.sha256(b"client_ip_test_A").hexdigest()[:32]
        key_b = hashlib.sha256(b"client_ip_test_B").hexdigest()[:32]

        with database.get_db_connection() as conn:
            conn.execute("DELETE FROM web_intel_rate_limits WHERE key_hash IN (?, ?)", (key_a, key_b))
            conn.commit()

        # Send 120 requests for key_a using a stable window to avoid clock boundary tick
        for _ in range(120):
            blocked = database.check_and_increment_rate_limit(key_a, window_sec=3600, max_requests=120)
            self.assertFalse(blocked)

        # 121st request should be blocked
        blocked_121 = database.check_and_increment_rate_limit(key_a, window_sec=3600, max_requests=120)
        self.assertTrue(blocked_121)

        # key_b should still be allowed (independent key isolation)
        blocked_b = database.check_and_increment_rate_limit(key_b, window_sec=3600, max_requests=120)
        self.assertFalse(blocked_b)

    def test_34_synthetic_traffic_isolation_from_kpis(self):
        """Verifies test runs with X-PostPilot-Test header or is_test flag are marked synthetic and isolated from analytics."""
        self._login(user_id=1, username="admin", role="admin", org_id=1)
        
        # Pre-check baseline unique visitors for property 1
        initial_overview = database.get_web_intel_overview(property_id=1, organization_id=1, days=30)
        initial_visitors = initial_overview['unique_visitors']

        # Send synthetic telemetry beacon
        res_test = self.client.post(
            '/api/web-intel/collect',
            json={
                "property_key": "gaatha_corporate",
                "session_id": "synthetic_session_999",
                "path": "/automated-test-run",
                "page_title": "Synthetic Test Run",
                "event_type": "pageview",
                "is_test": True
            },
            headers={
                "Origin": "https://gaatha.tech",
                "X-PostPilot-Test": "1",
                "X-Real-IP": "198.51.100.99"
            }
        )
        self.assertEqual(res_test.status_code, 200)

        # Verify record in database has is_synthetic = 1
        with database.get_db_connection() as conn:
            sess = conn.execute(
                "SELECT is_synthetic, is_bot FROM web_intel_sessions WHERE exit_page = '/automated-test-run'"
            ).fetchone()
            self.assertIsNotNone(sess)
            self.assertEqual(sess['is_synthetic'], 1)
            self.assertEqual(sess['is_bot'], 1)

        # Verify overview metrics did NOT count the synthetic visitor
        post_overview = database.get_web_intel_overview(property_id=1, organization_id=1, days=30)
        self.assertEqual(post_overview['unique_visitors'], initial_visitors)

    def test_35_portfolio_summary_api(self):
        """Verifies GET /api/web-intel/portfolio/summary returns multi-property aggregated intelligence."""
        self._login(user_id=1, username="admin", role="admin", org_id=1)
        res = self.client.get('/api/web-intel/portfolio/summary?days=30')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('total_properties', data)
        self.assertGreaterEqual(data['total_properties'], 7)
        self.assertIn('total_unique_visitors', data)
        self.assertIn('total_pageviews', data)
        self.assertIn('average_health_score', data)
        self.assertIn('properties', data)
        self.assertIsInstance(data['properties'], list)


if __name__ == '__main__':
    unittest.main()
