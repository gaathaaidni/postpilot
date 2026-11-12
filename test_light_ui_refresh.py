import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from app import app
import database


ROOT = Path(__file__).resolve().parent


class TestLightUiRefresh(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        database.init_db()

    def tearDown(self):
        self.app_context.pop()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1
            sess['csrf_token'] = 'test_csrf_token'

    def test_templates_default_light_theme(self):
        templates = [
            'templates/index.html',
            'templates/login.html',
            'templates/about.html',
            'templates/privacy.html',
            'templates/terms.html',
            'templates/user-agreement.html',
        ]
        for rel in templates:
            content = (ROOT / rel).read_text(encoding='utf-8')
            self.assertNotIn('data-theme="dark"', content.split('>', 1)[0], f'{rel} must not default to data-theme="dark" on <html>')
            self.assertIn("localStorage.getItem('postpilot_theme_v2') === 'dark'", content, f'{rel} must opt-in to optional dark mode via postpilot_theme_v2')

    def test_style_css_design_tokens_and_responsive_rules(self):
        css = (ROOT / 'static/style.css').read_text(encoding='utf-8')
        for required in [
            '--bg-app: #f8f9fb;',
            '--primary: #2563eb;',
            '--accent-gold: #b8860b;',
            '[data-theme="dark"]',
            'body.sidebar-collapsed',
            '.calendar-week-grid',
            '.mobile-posts-list',
            '.badge-draft',
            '.badge-scheduled',
            '.badge-publishing',
            '.badge-published',
            '.badge-failed',
            '--success-soft: var(--success-light);',
            '--warning-soft: var(--warning-light);',
            '--danger-soft: var(--danger-light);',
            '.hub-hero',
            '.notice-callout',
            '.theme-choice-card',
        ]:
            self.assertIn(required, css, f'style.css missing required token or selector: {required}')

    def test_script_js_no_fabricated_metrics_and_preserves_controls(self):
        js = (ROOT / 'static/script.js').read_text(encoding='utf-8')
        for forbidden in [
            'fb_post_sim_1794230000',
            'ig_media_sim_1794230100',
            'Cancelled Fixtures',
            'Audit Verified',
            '>100.0%</p>',
            '|| 18;',
        ]:
            self.assertNotIn(forbidden, js, f'script.js must not contain fabricated/hardcoded fixture: {forbidden}')

        for required_symbol in [
            'function initTheme()',
            'function setTheme(mode)',
            'function toggleTheme()',
            'function initSidebarCollapse()',
            'function toggleSidebarCollapse()',
            'function renderHelpAboutView(',
            'function renderDashboard(',
            'function loadIntegrationsDashboard(',
            'function openModal(',
            'function savePost()',
            'function renderHistory(',
            'function renderQueueTable(',
            'function renderSettings(',
            'function parseUtcTimestamp(',
            'function formatReadableDateTime(',
        ]:
            self.assertIn(required_symbol, js, f'script.js missing required function: {required_symbol}')

        # Verify every format* helper call in script.js has a matching function definition
        import re
        defs = set(re.findall(r'function\s+([A-Za-z0-9_]+)\s*\(', js))
        fmt_calls = set(re.findall(r'(?<!\.)\b(format[A-Za-z0-9_]*)\s*\(', js))
        self.assertEqual(sorted(c for c in fmt_calls if c not in defs), [], 'Undefined format* helper found in script.js')


    def test_public_and_authenticated_routes_and_guardrail(self):
        with patch.object(config, 'LOCAL_MODE', False):
            login_res = self.client.get('/login')
            self.assertEqual(login_res.status_code, 200, 'Expected HTTP 200 on /login when unauthenticated')
            login_html = login_res.data.decode('utf-8')
            self.assertNotIn('data-theme="dark"', login_html.split('>', 1)[0])

        for route in ['/about', '/privacy', '/terms', '/agreement']:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200, f'Expected HTTP 200 on {route}')

        self._login()
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        html = home.data.decode('utf-8')
        self.assertIn('id="theme-toggle-btn"', html)
        self.assertIn('id="sidebar-collapse-btn"', html)
        self.assertIn('id="modal-validation-alert"', html)
        self.assertIn('id="post-schedule-datetime"', html)

        status_res = self.client.get('/api/status')
        self.assertEqual(status_res.status_code, 200)
        status_data = json.loads(status_res.data)
        self.assertFalse(bool(status_data.get('publishing_enabled')), 'Publishing guardrail must remain disabled (0)')


if __name__ == '__main__':
    unittest.main()
