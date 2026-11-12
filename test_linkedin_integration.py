"""
test_linkedin_integration.py - PostPilot Dual LinkedIn Integration Test Suite

Comprehensive test coverage for:
1. Both applications' independent OAuth configurations (Aidni Global LLP & Gaatha Ventures Sh.p.k.)
2. Correct Client ID and Secret selection without mixing credentials
3. OAuth state generation, format (<app_key>:<csrf>), and CSRF validation
4. Separate token storage and complete token isolation between applications
5. Token expiry handling (active vs expired tokens)
6. Organization ID and URN formatting (145240694 and 145250613)
7. Organization permission checks when member has admin role
8. Missing Community Management API approval (personal posting allowed vs company page posting unavailable)
9. Modern LinkedIn REST Posts API request formatting (endpoint, LinkedIn-Version, headers, payload)
10. Publishing disabled safety guardrail (POSTPILOT_PUBLISHING_ENABLED=0)
11. Zero credential exposure (masking & log sanitization)
12. Application endpoints (/api/auth/linkedin/connect, callback, /api/linkedin/status)
"""
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import linkedin_api
import app as flask_app


class TestLinkedInDualIntegration(unittest.TestCase):

    def setUp(self):
        self.app = flask_app.app
        self.client = self.app.test_client()

    # --------------------------------------------------------------------------
    # 1. Independent OAuth Configurations
    # --------------------------------------------------------------------------
    def test_01_both_applications_independent_oauth_configurations(self):
        """Verifies both applications have independent configurations, org IDs, and names."""
        with patch.object(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', 'aidni_cid_111'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', 'aidni_secret_222'), \
             patch.object(config, 'LINKEDIN_ORG_ID_AIDNI_GLOBAL', '145240694'), \
             patch.object(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', 'gaatha_cid_333'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', 'gaatha_secret_444'), \
             patch.object(config, 'LINKEDIN_ORG_ID_GAATHA_VENTURES', '145250613'):

            aidni_cfg = linkedin_api.get_app_config('aidni_global')
            self.assertEqual(aidni_cfg['app_key'], 'aidni_global')
            self.assertEqual(aidni_cfg['display_name'], 'Aidni Global LLP')
            self.assertEqual(aidni_cfg['client_id'], 'aidni_cid_111')
            self.assertEqual(aidni_cfg['client_secret'], 'aidni_secret_222')
            self.assertEqual(aidni_cfg['org_id'], '145240694')
            self.assertEqual(aidni_cfg['org_urn'], 'urn:li:organization:145240694')

            gaatha_cfg = linkedin_api.get_app_config('gaatha_ventures')
            self.assertEqual(gaatha_cfg['app_key'], 'gaatha_ventures')
            self.assertEqual(gaatha_cfg['display_name'], 'Gaatha Ventures Sh.p.k.')
            self.assertEqual(gaatha_cfg['client_id'], 'gaatha_cid_333')
            self.assertEqual(gaatha_cfg['client_secret'], 'gaatha_secret_444')
            self.assertEqual(gaatha_cfg['org_id'], '145250613')
            self.assertEqual(gaatha_cfg['org_urn'], 'urn:li:organization:145250613')

    # --------------------------------------------------------------------------
    # 2. Correct Client ID & Secret Selection
    # --------------------------------------------------------------------------
    @patch('requests.post')
    def test_02_correct_client_id_and_secret_selection(self, mock_post):
        """Verifies authorization URL and token exchange select the exact app credentials."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'access_token': 'AIDNI_EXCHANGED_TOKEN_999',
            'expires_in': 5184000,
            'scope': 'openid profile email w_member_social'
        }
        mock_post.return_value = mock_resp

        with patch.object(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', 'aidni_client_unique_id'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', 'aidni_secret_unique_key'), \
             patch.object(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', 'gaatha_client_unique_id'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', 'gaatha_secret_unique_key'):

            # Auth URL check for Aidni
            url_aidni, state_aidni, _ = linkedin_api.get_authorization_url(app_key='aidni_global')
            self.assertIn("client_id=aidni_client_unique_id", url_aidni)
            self.assertNotIn("gaatha_client_unique_id", url_aidni)

            # Auth URL check for Gaatha
            url_gaatha, state_gaatha, _ = linkedin_api.get_authorization_url(app_key='gaatha_ventures')
            self.assertIn("client_id=gaatha_client_unique_id", url_gaatha)
            self.assertNotIn("aidni_client_unique_id", url_gaatha)

            # Token exchange check for Aidni
            with patch('linkedin_api.save_token_data'):
                res = linkedin_api.exchange_code_for_token('code_aidni_123', app_key='aidni_global')
                self.assertTrue(res['success'])
                post_data = mock_post.call_args[1]['data']
                self.assertEqual(post_data['client_id'], 'aidni_client_unique_id')
                self.assertEqual(post_data['client_secret'], 'aidni_secret_unique_key')

    # --------------------------------------------------------------------------
    # 3. OAuth State Generation & CSRF Validation
    # --------------------------------------------------------------------------
    def test_03_oauth_state_generation_and_csrf_validation(self):
        """Verifies state format '<app>:<csrf>', valid matches, and rejection of CSRF tampering."""
        state, csrf = linkedin_api.generate_oauth_state('aidni_global')
        self.assertTrue(state.startswith('aidni_global:'))
        self.assertEqual(state.split(':', 1)[1], csrf)

        # Valid state check
        is_valid, app_key, err = linkedin_api.validate_oauth_state(state, expected_csrf=csrf)
        self.assertTrue(is_valid)
        self.assertEqual(app_key, 'aidni_global')
        self.assertIsNone(err)

        # Tampered CSRF check
        is_valid_tampered, _, err_tampered = linkedin_api.validate_oauth_state(state, expected_csrf='FORGED_CSRF')
        self.assertFalse(is_valid_tampered)
        self.assertIn("CSRF", err_tampered)

        # Missing state check
        is_valid_none, _, _ = linkedin_api.validate_oauth_state(None)
        self.assertFalse(is_valid_none)

        # Unrecognized app check
        is_valid_unknown, _, err_unknown = linkedin_api.validate_oauth_state('unknown_company:csrf123')
        self.assertFalse(is_valid_unknown)
        self.assertIn("Unrecognized", err_unknown)

    # --------------------------------------------------------------------------
    # 4. Separate Token Storage & Complete Isolation
    # --------------------------------------------------------------------------
    def test_04_separate_token_storage_and_isolation(self):
        """Verifies each application's access token is stored and retrieved independently."""
        aidni_token_record = {
            'access_token': 'AIDNI_TOKEN_AAA',
            'expires_in': 3600,
            'scope': 'openid profile email w_member_social'
        }
        gaatha_token_record = {
            'access_token': 'GAATHA_TOKEN_GGG',
            'expires_in': 7200,
            'scope': 'openid profile email w_member_social'
        }

        with patch('linkedin_api._write_token_store_to_disk'), \
             patch('linkedin_api._load_token_store_from_disk', return_value={}):

            linkedin_api.save_token_data('aidni_global', aidni_token_record)
            linkedin_api.save_token_data('gaatha_ventures', gaatha_token_record)

            retrieved_aidni = linkedin_api.get_active_token('aidni_global')
            retrieved_gaatha = linkedin_api.get_active_token('gaatha_ventures')

            self.assertEqual(retrieved_aidni, 'AIDNI_TOKEN_AAA')
            self.assertEqual(retrieved_gaatha, 'GAATHA_TOKEN_GGG')
            self.assertNotEqual(retrieved_aidni, retrieved_gaatha)

    # --------------------------------------------------------------------------
    # 5. Token Expiry Handling
    # --------------------------------------------------------------------------
    def test_05_token_expiry_handling(self):
        """Verifies active tokens are valid and expired tokens are rejected."""
        # Active token
        active_record = {
            'access_token': 'VALID_TOKEN',
            'expires_at': time.time() + 3600
        }
        self.assertFalse(linkedin_api.is_token_expired(active_record))

        # Expired token
        expired_record = {
            'access_token': 'EXPIRED_TOKEN',
            'expires_at': time.time() - 100
        }
        self.assertTrue(linkedin_api.is_token_expired(expired_record))

        # Empty record
        self.assertTrue(linkedin_api.is_token_expired(None))

    # --------------------------------------------------------------------------
    # 6. Organization ID and URN Handling
    # --------------------------------------------------------------------------
    def test_06_organization_id_and_urn_handling(self):
        """Verifies organization IDs are correctly parsed and formatted into URNs."""
        cfg_aidni = linkedin_api.get_app_config('aidni_global')
        self.assertEqual(cfg_aidni['org_id'], '145240694')
        self.assertEqual(cfg_aidni['org_urn'], 'urn:li:organization:145240694')

        cfg_gaatha = linkedin_api.get_app_config('gaatha_ventures')
        self.assertEqual(cfg_gaatha['org_id'], '145250613')
        self.assertEqual(cfg_gaatha['org_urn'], 'urn:li:organization:145250613')

    # --------------------------------------------------------------------------
    # 7. Organization Permission Checks (Admin Role)
    # --------------------------------------------------------------------------
    @patch('requests.get')
    def test_07_organization_permission_checks_when_admin(self, mock_get):
        """Verifies admin role approval when Community Management API is present."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'elements': [
                {
                    'role': 'ADMINISTRATOR',
                    'state': 'APPROVED',
                    'organizationalTarget': 'urn:li:organization:145250613'
                }
            ]
        }
        mock_get.return_value = mock_resp

        # Mock token data with w_organization_social
        token_data = {
            'access_token': 'MOCK_ADMIN_TOKEN',
            'expires_at': time.time() + 3600,
            'scope': 'openid profile email w_member_social w_organization_social'
        }

        with patch('linkedin_api.get_token_data', return_value=token_data), \
             patch('linkedin_api.get_active_token', return_value='MOCK_ADMIN_TOKEN'):

            elig = linkedin_api.check_organization_publishing_eligibility('gaatha_ventures')
            self.assertTrue(elig['company_publishing_authorized'])
            self.assertEqual(elig['eligibility_code'], 'AUTHORIZED')
            self.assertIn("authorized", elig['eligibility_message'].lower())

    # --------------------------------------------------------------------------
    # 8. Missing Community Management API Approval
    # --------------------------------------------------------------------------
    def test_08_missing_community_management_api_approval(self):
        """Verifies clear distinction: personal posting allowed vs company publishing unavailable."""
        # Standard token with confirmed scopes only
        token_data = {
            'access_token': 'STANDARD_MEMBER_TOKEN',
            'expires_at': time.time() + 3600,
            'scope': 'openid profile email w_member_social'
        }

        with patch('linkedin_api.get_token_data', return_value=token_data), \
             patch('linkedin_api.get_active_token', return_value='STANDARD_MEMBER_TOKEN'):

            elig = linkedin_api.check_organization_publishing_eligibility('aidni_global')
            self.assertTrue(elig['personal_posting_available'])
            self.assertFalse(elig['company_publishing_authorized'])
            self.assertEqual(elig['eligibility_code'], 'COMMUNITY_MANAGEMENT_API_REQUIRED')
            self.assertIn("Community Management API access has not been approved", elig['eligibility_message'])
            self.assertIn("w_organization_social", elig['required_scopes'])

    # --------------------------------------------------------------------------
    # 9. LinkedIn REST Posts API Request Formatting
    # --------------------------------------------------------------------------
    @patch('requests.post')
    def test_09_linkedin_rest_posts_api_request_formatting(self, mock_post):
        """Verifies requests use modern /rest/posts endpoint, version header, and payload structure."""
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.headers = {'x-restli-id': 'urn:li:share:9876543210'}
        mock_resp.json.return_value = {'id': 'urn:li:share:9876543210'}
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '1'}), \
             patch('linkedin_api.get_active_token', return_value='TEST_BEARER_TOKEN'):

            self.assertTrue(config.is_publishing_enabled())
            res = linkedin_api.create_organization_post(
                organization_id="145240694",
                text="Official announcement from Aidni Global LLP",
                app_key="aidni_global"
            )
            self.assertTrue(res['success'])
            self.assertEqual(res['id'], 'urn:li:share:9876543210')

            mock_post.assert_called_once()
            called_url = mock_post.call_args[0][0]
            self.assertEqual(called_url, linkedin_api.REST_POSTS_URL)
            self.assertEqual(called_url, "https://api.linkedin.com/rest/posts")

            called_headers = mock_post.call_args[1]['headers']
            self.assertEqual(called_headers['LinkedIn-Version'], linkedin_api.get_rest_api_version())
            self.assertEqual(called_headers['LinkedIn-Version'], '202610')
            self.assertEqual(called_headers['X-Restli-Protocol-Version'], '2.0.0')
            self.assertEqual(called_headers['Authorization'], 'Bearer TEST_BEARER_TOKEN')

            called_payload = mock_post.call_args[1]['json']
            self.assertEqual(called_payload['author'], 'urn:li:organization:145240694')
            self.assertEqual(called_payload['commentary'], 'Official announcement from Aidni Global LLP')
            self.assertEqual(called_payload['visibility'], 'PUBLIC')
            self.assertEqual(called_payload['lifecycleState'], 'PUBLISHED')
            self.assertEqual(called_payload['distribution']['feedDistribution'], 'MAIN_FEED')

    # --------------------------------------------------------------------------
    # 10. Publishing Safety Disabled Guardrail
    # --------------------------------------------------------------------------
    @patch('requests.post')
    def test_10_publishing_safety_disabled_guardrail(self, mock_post):
        """Verifies publishing is simulated and external network calls are strictly blocked."""
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled())

            res = linkedin_api.create_organization_post(
                organization_id="145250613",
                text="Safety test post for Gaatha Ventures",
                app_key="gaatha_ventures"
            )
            self.assertTrue(res['success'])
            self.assertTrue(res['simulated'])
            self.assertIn("Simulated publishing", res['message'])
            # Must NEVER call external network
            mock_post.assert_not_called()

    # --------------------------------------------------------------------------
    # 11. Zero Credential Exposure
    # --------------------------------------------------------------------------
    def test_11_zero_credential_exposure(self):
        """Verifies credentials, tokens, and authorization codes are masked and sanitized."""
        token = "AQUTestSecretAccessToken987654321"
        masked = linkedin_api.mask_secret_preview(token)
        self.assertEqual(masked, "AQUT...4321")

        log_raw = "Failed exchanging code=AUTH_CODE_SECRET_999 with client_secret=MY_CLIENT_SECRET"
        clean = linkedin_api.sanitize_log_message(log_raw)
        self.assertNotIn("AUTH_CODE_SECRET_999", clean)
        self.assertNotIn("MY_CLIENT_SECRET", clean)
        self.assertIn("[REDACTED]", clean)

    # --------------------------------------------------------------------------
    # 12. Application Endpoints (Connect, Callback, Status)
    # --------------------------------------------------------------------------
    def test_12_application_endpoints(self):
        """Tests Flask REST endpoints for dual application connect, callback, and status."""
        with patch.object(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', 'aidni_id_555'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', 'aidni_sec_555'), \
             patch.object(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', 'gaatha_id_777'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', 'gaatha_sec_777'):

            with self.client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['username'] = 'admin'
                sess['role'] = 'admin'
                sess['organization_id'] = 1

            # Test Connect for Aidni
            resp_aidni = self.client.get('/api/auth/linkedin/connect?app=aidni_global&format=json')
            self.assertEqual(resp_aidni.status_code, 200)
            data_aidni = resp_aidni.get_json()
            self.assertTrue(data_aidni['success'])
            self.assertEqual(data_aidni['app_key'], 'aidni_global')
            self.assertIn('client_id=aidni_id_555', data_aidni['authorization_url'])

            # Test Connect for Gaatha
            resp_gaatha = self.client.get('/api/auth/linkedin/connect?app=gaatha_ventures&format=json')
            self.assertEqual(resp_gaatha.status_code, 200)
            data_gaatha = resp_gaatha.get_json()
            self.assertTrue(data_gaatha['success'])
            self.assertEqual(data_gaatha['app_key'], 'gaatha_ventures')
            self.assertIn('client_id=gaatha_id_777', data_gaatha['authorization_url'])

            # Test Status endpoint
            resp_status = self.client.get('/api/linkedin/status')
            self.assertEqual(resp_status.status_code, 200)
            status_json = resp_status.get_json()
            self.assertIn('apps', status_json)
            self.assertIn('aidni_global', status_json['apps'])
            self.assertIn('gaatha_ventures', status_json['apps'])

    # --------------------------------------------------------------------------
    # 13. Redirect URI Exactness & Session/Credential Isolation
    # --------------------------------------------------------------------------
    def test_13_redirect_uri_exactness_and_token_isolation(self):
        """Verifies exact production redirect_uri match across both apps and strict token isolation."""
        import urllib.parse
        expected_uri = 'https://postpilot.gaatha.tech/api/auth/linkedin/callback'

        with patch.object(config, 'LINKEDIN_REDIRECT_URI', expected_uri), \
             patch.object(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', 'aidni_cid_exact'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', 'aidni_sec_exact'), \
             patch.object(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', 'gaatha_cid_exact'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', 'gaatha_sec_exact'):

            with self.client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['username'] = 'admin'
                sess['role'] = 'admin'
                sess['organization_id'] = 1

            # Initiate both OAuth flows sequentially before completing callbacks
            r_aidni = self.client.get('/api/auth/linkedin/connect?app=aidni_global&format=json')
            r_gaatha = self.client.get('/api/auth/linkedin/connect?app=gaatha_ventures&format=json')
            self.assertEqual(r_aidni.status_code, 200)
            self.assertEqual(r_gaatha.status_code, 200)

            d_aidni = r_aidni.get_json()
            d_gaatha = r_gaatha.get_json()

            for d, expected_scope in (
                (d_aidni, 'openid profile email w_member_social'),
                (d_gaatha, 'w_member_social'),
            ):
                parsed = urllib.parse.urlparse(d['authorization_url'])
                qs = urllib.parse.parse_qs(parsed.query)
                self.assertEqual(qs['redirect_uri'][0], expected_uri)
                self.assertFalse(qs['redirect_uri'][0].endswith('/'))
                self.assertTrue(qs['redirect_uri'][0].startswith('https://'))
                self.assertEqual(qs['scope'][0], expected_scope)

            # Complete callback for Aidni Global while Gaatha Ventures OAuth is still pending
            with patch('linkedin_api.exchange_code_for_token') as mock_exch, \
                 patch('linkedin_api.check_organization_publishing_eligibility', return_value={'company_publishing_authorized': False}), \
                 patch('linkedin_api.get_authenticated_member', return_value={'success': True, 'name': 'Aidni User'}), \
                 patch('database.upsert_social_account'):

                mock_exch.return_value = {
                    'success': True,
                    'app_key': 'aidni_global',
                    'display_name': 'Aidni Global LLP',
                    'access_token': 'TOK_AIDNI_ONLY',
                    'expires_in': 5184000,
                    'expires_at': time.time() + 5184000,
                    'scope': 'openid profile email w_member_social',
                    'member': {'success': True, 'name': 'Aidni User'}
                }

                cb_aidni = self.client.get(
                    f"/api/auth/linkedin/callback?code=code_a&state={urllib.parse.quote(d_aidni['state'])}&format=json"
                )
                self.assertEqual(cb_aidni.status_code, 200)

                # Now complete callback for Gaatha Ventures — its CSRF state must still be valid!
                mock_exch.return_value = {
                    'success': True,
                    'app_key': 'gaatha_ventures',
                    'display_name': 'Gaatha Ventures Sh.p.k.',
                    'access_token': 'TOK_GAATHA_ONLY',
                    'expires_in': 5184000,
                    'expires_at': time.time() + 5184000,
                    'scope': 'openid profile email w_member_social',
                    'member': {'success': True, 'name': 'Gaatha User'}
                }
                cb_gaatha = self.client.get(
                    f"/api/auth/linkedin/callback?code=code_g&state={urllib.parse.quote(d_gaatha['state'])}&format=json"
                )
                self.assertEqual(cb_gaatha.status_code, 200)

            with self.client.session_transaction() as sess:
                self.assertEqual(sess.get('linkedin_access_token_aidni_global'), 'TOK_AIDNI_ONLY')
                self.assertEqual(sess.get('linkedin_access_token_gaatha_ventures'), 'TOK_GAATHA_ONLY')
                self.assertNotIn('linkedin_access_token', sess)


    # --------------------------------------------------------------------------
    # 14. Per-App Scope Isolation (Aidni OpenID+Share vs Gaatha Share-only)
    # --------------------------------------------------------------------------
    def test_14_per_app_scope_isolation_and_overrides(self):
        """Verifies Aidni Global retains OpenID+Share while Gaatha Ventures defaults to w_member_social."""
        import urllib.parse
        with patch.object(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', 'aidni_cid'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', 'aidni_sec'), \
             patch.object(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', 'gaatha_cid'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', 'gaatha_sec'):

            url_aidni, _, _ = linkedin_api.get_authorization_url('aidni_global')
            aidni_qs = urllib.parse.parse_qs(urllib.parse.urlparse(url_aidni).query)
            self.assertEqual(aidni_qs['scope'][0].split(), ['openid', 'profile', 'email', 'w_member_social'])

            url_gaatha, _, _ = linkedin_api.get_authorization_url('gaatha_ventures')
            gaatha_qs = urllib.parse.parse_qs(urllib.parse.urlparse(url_gaatha).query)
            self.assertEqual(gaatha_qs['scope'][0].split(), ['w_member_social'])
            self.assertNotIn('openid', gaatha_qs['scope'][0])
            self.assertNotIn('w_organization_social', gaatha_qs['scope'][0])

            with patch.dict(os.environ, {'LINKEDIN_SCOPES_GAATHA_VENTURES': 'w_member_social,w_organization_social'}):
                url_custom, _, _ = linkedin_api.get_authorization_url('gaatha_ventures')
                custom_qs = urllib.parse.parse_qs(urllib.parse.urlparse(url_custom).query)
                self.assertEqual(custom_qs['scope'][0].split(), ['w_member_social', 'w_organization_social'])

    # --------------------------------------------------------------------------
    # 15. Comma-Separated Scope Parsing & Token Introspection
    # --------------------------------------------------------------------------
    @patch('requests.post')
    def test_15_comma_separated_scope_parsing_and_introspection(self, mock_post):
        """Verifies comma-separated LinkedIn scopes parse cleanly and introspect_token uses app credentials."""
        self.assertEqual(
            linkedin_api.parse_scopes('email,openid,profile,w_member_social'),
            ['email', 'openid', 'profile', 'w_member_social'],
        )
        token_data = {
            'access_token': 'COMMA_SCOPES_TOK',
            'expires_at': time.time() + 3600,
            'scope': 'email,openid,profile,w_member_social',
        }
        with patch('linkedin_api.get_token_data', return_value=token_data), \
             patch('linkedin_api.get_active_token', return_value='COMMA_SCOPES_TOK'):
            elig = linkedin_api.check_organization_publishing_eligibility('aidni_global')
            self.assertTrue(elig['personal_posting_available'])
            self.assertFalse(elig['company_publishing_authorized'])

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'active': True,
            'status': 'active',
            'scope': 'w_member_social',
            'auth_type': '3L',
        }
        mock_post.return_value = mock_resp

        with patch.object(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', 'gaatha_cid_intro'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', 'gaatha_sec_intro'):
            res = linkedin_api.introspect_token('gaatha_ventures', 'GAATHA_TOK_XYZ')
            self.assertTrue(res['checked'])
            self.assertTrue(res['active'])
            self.assertEqual(res['scopes'], ['w_member_social'])
            self.assertEqual(mock_post.call_args[0][0], 'https://www.linkedin.com/oauth/v2/introspectToken')
            self.assertEqual(mock_post.call_args[1]['data']['client_id'], 'gaatha_cid_intro')
            self.assertEqual(mock_post.call_args[1]['data']['client_secret'], 'gaatha_sec_intro')

    # --------------------------------------------------------------------------
    # 16. Callback Error Handling Without Crash / HTTP 500
    # --------------------------------------------------------------------------
    def test_16_callback_error_handling_browser_redirect_no_500(self):
        """Verifies OAuth error callbacks redirect safely to Accounts tab instead of crashing on urllib."""
        import urllib.parse
        import app as postpilot_app
        client = postpilot_app.app.test_client()

        resp = client.get(
            '/api/auth/linkedin/callback?error=unauthorized_scope_error&error_description=Scope+not+authorized&state=gaatha_ventures:csrf123',
            headers={'Accept': 'text/html'},
        )
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers.get('Location', '')
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
        self.assertEqual(qs.get('tab'), ['accounts'])
        self.assertEqual(qs.get('linkedin_error'), ['unauthorized_scope_error'])
        self.assertEqual(qs.get('linkedin_app'), ['gaatha_ventures'])

        resp_json = client.get(
            '/api/auth/linkedin/callback?error=unauthorized_scope_error&error_description=Scope+not+authorized',
            headers={'Accept': 'application/json'},
        )
        self.assertEqual(resp_json.status_code, 400)
        self.assertEqual(resp_json.get_json().get('code'), 'OAUTH_DENIED')

    # --------------------------------------------------------------------------
    # 17. Share-Only Token Validation & Honest Account Status
    # --------------------------------------------------------------------------
    def test_17_gaatha_w_member_social_status_and_accounts_honesty(self):
        """Verifies w_member_social-only tokens validate via introspection and unauthenticated rows never fake connected."""
        import integrations_service
        import database
        import app as postpilot_app

        database.init_db()
        gaatha_tok = {
            'access_token': 'GAATHA_SHARE_ONLY_TOK',
            'expires_at': time.time() + 3600,
            'scope': 'w_member_social',
        }
        with patch('linkedin_api.get_active_token', side_effect=lambda k: 'GAATHA_SHARE_ONLY_TOK' if k == 'gaatha_ventures' else None), \
             patch('linkedin_api.get_token_data', side_effect=lambda k: gaatha_tok if k == 'gaatha_ventures' else None), \
             patch('linkedin_api.introspect_token', return_value={'checked': True, 'active': True, 'scopes': ['w_member_social']}), \
             patch('linkedin_api.get_authenticated_member') as mock_userinfo:
            status = integrations_service.get_linkedin_integration_status()
            mock_userinfo.assert_not_called()
            apps = {a['app_key']: a for a in status['apps']}
            self.assertTrue(apps['gaatha_ventures']['user_authenticated'])
            self.assertEqual(apps['gaatha_ventures']['token_scopes'], ['w_member_social'])
            self.assertEqual(apps['gaatha_ventures']['requested_scopes'], ['w_member_social'])
            self.assertFalse(apps['gaatha_ventures']['company_publishing_ready'])
            self.assertIn('Limited', apps['gaatha_ventures']['status_label'])

        client = postpilot_app.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1

        with patch('linkedin_api.get_token_data', return_value=None):
            acc_resp = client.get('/api/accounts')
            self.assertEqual(acc_resp.status_code, 200)
            li_accs = {a.get('app_identifier'): a for a in acc_resp.get_json()['accounts'] if a['platform'] == 'linkedin'}
            self.assertEqual(li_accs['gaatha_ventures']['status'], 'authentication_required')
            self.assertEqual(li_accs['gaatha_ventures']['token_status'], 'missing')
            self.assertEqual(li_accs['gaatha_ventures']['permissions_scope'], 'w_member_social')

    # --------------------------------------------------------------------------
    # 18. Aidni Global Preservation During Gaatha OAuth Callback
    # --------------------------------------------------------------------------
    @patch('requests.post')
    def test_18_aidni_preservation_during_gaatha_oauth_flow(self, mock_post):
        """Verifies completing Gaatha Ventures OAuth preserves Aidni Global's existing token store and DB mapping."""
        import app as postpilot_app

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'access_token': 'GAATHA_NEW_TOKEN_777',
            'expires_in': 5184000,
            'scope': 'w_member_social',
        }
        mock_post.return_value = mock_resp

        aidni_expires_at = time.time() + 5000000
        mem_store = {
            'aidni_global': {
                'access_token': 'AIDNI_LIVE_TOKEN_PROTECTED',
                'expires_in': 5183999,
                'expires_at': aidni_expires_at,
                'scope': 'email,openid,profile,w_member_social',
            }
        }

        def fake_load():
            return dict(mem_store)

        def fake_write(data):
            mem_store.clear()
            mem_store.update(data)

        client = postpilot_app.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1
            sess['linkedin_oauth_states'] = {'gaatha_ventures': 'gaatha_csrf_ok'}

        with patch.object(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', 'gaatha_cid_live'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', 'gaatha_sec_live'), \
             patch.object(config, 'LINKEDIN_REDIRECT_URI', 'https://postpilot.gaatha.tech/api/auth/linkedin/callback'), \
             patch('linkedin_api._load_token_store_from_disk', side_effect=fake_load), \
             patch('linkedin_api._write_token_store_to_disk', side_effect=fake_write), \
             patch('linkedin_api.get_authenticated_member') as mock_userinfo, \
             patch('database.upsert_social_account') as mock_upsert:

            cb_resp = client.get(
                '/api/auth/linkedin/callback?code=gaatha_auth_code_123&state=gaatha_ventures:gaatha_csrf_ok',
                headers={'Accept': 'text/html'},
            )
            self.assertEqual(cb_resp.status_code, 302)
            self.assertIn('linkedin_connected=gaatha_ventures', cb_resp.headers.get('Location', ''))
            mock_userinfo.assert_not_called()

            # Verify token exchange used Gaatha credentials + exact redirect_uri
            post_data = mock_post.call_args[1]['data']
            self.assertEqual(post_data['client_id'], 'gaatha_cid_live')
            self.assertEqual(post_data['client_secret'], 'gaatha_sec_live')
            self.assertEqual(post_data['redirect_uri'], 'https://postpilot.gaatha.tech/api/auth/linkedin/callback')

            # Verify Aidni Global token completely untouched while Gaatha Ventures saved
            self.assertEqual(mem_store['aidni_global']['access_token'], 'AIDNI_LIVE_TOKEN_PROTECTED')
            self.assertEqual(mem_store['aidni_global']['expires_at'], aidni_expires_at)
            self.assertEqual(mem_store['gaatha_ventures']['access_token'], 'GAATHA_NEW_TOKEN_777')
            self.assertEqual(mem_store['gaatha_ventures']['scope'], 'w_member_social')

            # Verify DB upsert targeted Gaatha Ventures (145250613), never Aidni (145240694)
            mock_upsert.assert_called_once()
            upsert_kw = mock_upsert.call_args[1]
            self.assertEqual(upsert_kw['app_identifier'], 'gaatha_ventures')
            self.assertEqual(upsert_kw['account_identifier'], '145250613')


if __name__ == '__main__':
    unittest.main()
