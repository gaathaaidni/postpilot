import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import config
import database
import facebook_api
from app import app
from platform_adapters.whatsapp import PRESERVED_WHATSAPP_NUMBERS, WhatsAppCloudAdapter


class TestWhatsAppReadiness(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        database.init_db()
        self.adapter = WhatsAppCloudAdapter()

    def tearDown(self):
        self.app_context.pop()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1
            sess['csrf_token'] = 'test_csrf_token'

    def test_01_sandbox_simulation_makes_zero_external_http_calls(self):
        self._login()
        with patch.object(config, 'is_platform_publishing_enabled', return_value=False), \
             patch('requests.post') as mock_post, \
             patch('requests.request') as mock_req:
            res = self.adapter.send_template(
                '+91 98257-28291',
                'client_welcome',
                variables=['Gaatha Ventures'],
            )
            self.assertTrue(res.get('success'))
            self.assertTrue(res.get('simulated'))
            self.assertEqual(res.get('recipient_phone'), '+919825728291')
            self.assertTrue(str(res.get('external_message_id', '')).startswith('wamid.sim_'))

            # /api/whatsapp/simulate endpoint
            sim_res = self.client.post(
                '/api/whatsapp/simulate',
                json={
                    'recipient_phone': '+91 98257 28291',
                    'template_name': 'client_welcome',
                    'message': 'Welcome to Gaatha Ventures!',
                },
                headers={'X-CSRFToken': 'test_csrf_token'},
            )
            self.assertEqual(sim_res.status_code, 200)
            sim_data = json.loads(sim_res.data)
            self.assertTrue(sim_data.get('success'))
            self.assertTrue(sim_data.get('simulated'))

            # Direct /messages intercept in facebook_api._request_with_retry
            intercepted = facebook_api._request_with_retry(
                'POST',
                'https://graph.facebook.com/v19.0/1171737406016871/messages',
                json={'messaging_product': 'whatsapp', 'to': '919825728291'},
            )
            self.assertTrue(intercepted.get('simulated'))
            self.assertTrue(intercepted.get('success'))

            mock_post.assert_not_called()
            mock_req.assert_not_called()

    def test_02_publish_endpoint_blocks_whatsapp_when_disabled(self):
        self._login()
        with patch.object(config, 'is_platform_publishing_enabled', side_effect=lambda p: p != 'whatsapp'):
            res = self.client.post(
                '/api/publish',
                json={'platform': 'whatsapp', 'message': 'WhatsApp guardrail check', 'brand_id': 1},
                headers={'X-CSRFToken': 'test_csrf_token'},
            )
            self.assertEqual(res.status_code, 403)
            data = json.loads(res.data)
            self.assertTrue(data.get('blocked_by_guardrail'))

    def test_03_template_honesty_local_preview_never_marked_approved(self):
        previews = self.adapter.get_templates()
        self.assertGreaterEqual(len(previews), 4)
        for tpl in previews:
            self.assertEqual(tpl.get('status'), 'LOCAL_PREVIEW')
            self.assertFalse(tpl.get('meta_approved'))
            self.assertTrue(tpl.get('is_local_preview'))

        submittable = [t for t in previews if t.get('submission_ready')]
        self.assertEqual(len(submittable), 3)
        for t in submittable:
            self.assertIn('components', t['submission_payload'])

        # Mock live fetch returning 0 approved templates
        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': 'dummy_tok'}), \
             patch('requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'data': []}
            mock_get.return_value = mock_resp

            live_zero = self.adapter.fetch_live_templates(waba_id='1370721214882653')
            self.assertTrue(live_zero['success'])
            self.assertEqual(live_zero['approved_count'], 0)
            self.assertEqual(live_zero['templates'], [])

            # Mock live fetch returning 1 APPROVED template
            mock_resp.json.return_value = {
                'data': [{'id': 't1', 'name': 'client_welcome', 'status': 'APPROVED', 'category': 'UTILITY', 'language': 'en'}]
            }
            live_one = self.adapter.fetch_live_templates(waba_id='1471882524763501')
            self.assertTrue(live_one['success'])
            self.assertEqual(live_one['approved_count'], 1)
            self.assertTrue(live_one['templates'][0]['meta_approved'])

        # Verify /api/whatsapp/templates route response contract
        self._login()
        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': ''}):
            r = self.client.get('/api/whatsapp/templates')
            self.assertEqual(r.status_code, 200)
            d = json.loads(r.data)
            self.assertTrue(d['success'])
            self.assertEqual(d['meta_approved_count'], 0)
            self.assertEqual(d['local_previews_count'], 4)
            self.assertEqual(len(d['preserved_numbers']), len(PRESERVED_WHATSAPP_NUMBERS))

    def test_04_template_variable_and_content_validation(self):
        ok, err = self.adapter.validate_template_variables('Hello {{1}}, ref {{2}}', variables=['Gaatha', 'REF-1'])
        self.assertTrue(ok, err)

        ok_missing, _ = self.adapter.validate_template_variables('Hello {{1}}, ref {{2}}', variables=['Gaatha'])
        self.assertFalse(ok_missing)

        ok_gap, _ = self.adapter.validate_template_variables('Hello {{1}} and {{3}}', variables=['A', 'B', 'C'])
        self.assertFalse(ok_gap)

        ok_empty, _ = self.adapter.validate_template_variables('Hello {{1}}', variables=['   '])
        self.assertFalse(ok_empty)

        ok_newline, _ = self.adapter.validate_template_variables('Hello {{1}}', variables=['line1\nline2'])
        self.assertFalse(ok_newline)

        ok_len, _ = self.adapter.validate_content({'message': 'x' * 4097})
        self.assertFalse(ok_len)

        ok_name, _ = self.adapter.validate_content({'template_name': 'Invalid-Name!', 'message': 'ok'})
        self.assertFalse(ok_name)

    def test_05_e164_phone_validation(self):
        ok1, p1 = self.adapter.validate_phone_number('+91 98257-28291')
        self.assertTrue(ok1)
        self.assertEqual(p1, '+919825728291')

        ok2, p2 = self.adapter.validate_phone_number('+1 (555) 234-5678')
        self.assertTrue(ok2)
        self.assertEqual(p2, '+15552345678')

        for bad in ('', '123', '+0123456789', 'abc'):
            ok_bad, _ = self.adapter.validate_phone_number(bad)
            self.assertFalse(ok_bad, f"Expected '{bad}' to fail E.164 validation")

    def test_06_webhook_get_challenge_and_fail_closed_hmac_post(self):
        with patch.dict(os.environ, {'WHATSAPP_VERIFY_TOKEN': 'pp_verify_tok', 'WHATSAPP_APP_SECRET': ''}):
            res_ok = self.client.get('/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=pp_verify_tok&hub.challenge=987654')
            self.assertEqual(res_ok.status_code, 200)
            self.assertEqual(res_ok.data.decode('utf-8'), '987654')

            res_bad_tok = self.client.get('/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=987654')
            self.assertEqual(res_bad_tok.status_code, 403)

            # Fail closed when WHATSAPP_APP_SECRET missing
            res_no_secret = self.client.post(
                '/api/webhooks/whatsapp',
                data=b'{"entry":[]}',
                headers={'X-Hub-Signature-256': 'sha256=deadbeef', 'Content-Type': 'application/json'},
            )
            self.assertEqual(res_no_secret.status_code, 403)

        secret = 'super_webhook_secret_123'
        payload_dict = {
            'entry': [{
                'id': '1471882524763501',
                'changes': [{
                    'value': {
                        'metadata': {'phone_number_id': '1298748379987770'},
                        'statuses': [{'id': 'wamid.1', 'status': 'delivered', 'recipient_id': '919825728291'}],
                        'messages': [{'id': 'wamid.2', 'from': '919825728291', 'type': 'text', 'text': {'body': 'Hi'}}],
                    }
                }],
            }]
        }
        raw = json.dumps(payload_dict).encode('utf-8')
        good_sig = 'sha256=' + hmac.new(secret.encode('utf-8'), raw, hashlib.sha256).hexdigest()

        with patch.dict(os.environ, {'WHATSAPP_APP_SECRET': secret}):
            res_bad_sig = self.client.post(
                '/api/webhooks/whatsapp',
                data=raw,
                headers={'X-Hub-Signature-256': 'sha256=0000', 'Content-Type': 'application/json'},
            )
            self.assertEqual(res_bad_sig.status_code, 403)

            res_good_sig = self.client.post(
                '/api/webhooks/whatsapp',
                data=raw,
                headers={'X-Hub-Signature-256': good_sig, 'Content-Type': 'application/json'},
            )
            self.assertEqual(res_good_sig.status_code, 200)
            body = json.loads(res_good_sig.data)
            self.assertEqual(body.get('events_recorded'), 2)

            events = database.get_whatsapp_webhook_events(organization_id=1, limit=10)
            self.assertGreaterEqual(len(events), 2)

    def test_07_error_classification_and_token_health(self):
        diag_190 = self.adapter.classify_whatsapp_error(
            {'error': {'code': 190, 'message': 'Session expired EAAFAKE1234567890TOKEN'}}
        )
        self.assertEqual(diag_190['category'], 'AUTH_EXPIRED')
        self.assertNotIn('EAAFAKE1234567890TOKEN', diag_190['message'])

        self.assertEqual(self.adapter.classify_whatsapp_error({'error': {'code': 141006}})['category'], 'PAYMENT_METHOD_REQUIRED')
        self.assertEqual(self.adapter.classify_whatsapp_error({'error': {'code': 141007}})['category'], 'TIMEZONE_REQUIRED')
        self.assertEqual(self.adapter.classify_whatsapp_error({'error': {'code': 132000}})['category'], 'TEMPLATE_PARAM_ERROR')
        diag_rate = self.adapter.classify_whatsapp_error({'error': {'code': 130429}})
        self.assertEqual(diag_rate['category'], 'RATE_LIMIT')
        self.assertTrue(diag_rate['retryable'])

        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': 'tok_test'}), \
             patch('requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                'data': {
                    'is_valid': True,
                    'expires_at': 100,
                    'scopes': ['whatsapp_business_messaging'],
                }
            }
            mock_get.return_value = mock_resp
            health = self.adapter.check_token_health()
            self.assertFalse(health['valid'])
            self.assertTrue(health['expired'])
            self.assertIn('whatsapp_business_management', health['missing_scopes'])

    def test_08_sender_isolation_and_brand_isolation(self):
        with patch.dict(
            os.environ,
            {
                'WHATSAPP_ACTIVE_PHONE_NUMBER_ID': '1298748379987770',
                'WHATSAPP_INACTIVE_PHONE_NUMBER_IDS': '1171737406016871,999111222',
            },
        ):
            ok_active, pid, _ = self.adapter.validate_sender('1298748379987770')
            self.assertTrue(ok_active)
            self.assertEqual(pid, '1298748379987770')

            ok_inact, _, err_inact = self.adapter.validate_sender('999111222')
            self.assertFalse(ok_inact)
            self.assertIn('inactive', err_inact.lower())

            ok_sec, _, err_sec = self.adapter.validate_sender('1171737406016871')
            self.assertFalse(ok_sec)

            ok_mismatch, _, _ = self.adapter.validate_sender('999888777')
            self.assertFalse(ok_mismatch)

            res_blocked = self.adapter.send_template(
                '+919825728291',
                'client_welcome',
                phone_number_id='1171737406016871',
            )
            self.assertFalse(res_blocked['success'])

        # Brand 3 has no mapped WhatsApp account -> must fail closed cleanly
        brand_res = self.adapter.publish({
            'organization_id': 1,
            'brand_id': 3,
            'recipient_phone': '+919825728291',
            'template_name': 'client_welcome',
        })
        self.assertFalse(brand_res['success'])
        self.assertIn('Cross-brand inheritance blocked', brand_res['error'])

    def test_09_dual_account_representation_and_policy(self):
        import integrations_service
        from pathlib import Path

        # 1. Preferred sender must resolve ONLY to 1298748379987770 / WABA 1471882524763501
        #    while preserving legacy .env 1171737406016871 / 1370721214882653 untouched.
        with patch.dict(os.environ, {
            'WHATSAPP_PHONE_NUMBER_ID': '1171737406016871',
            'WHATSAPP_BUSINESS_ACCOUNT_ID': '1370721214882653',
            'WHATSAPP_ACTIVE_PHONE_NUMBER_ID': '',
            'WHATSAPP_ACTIVE_WABA_ID': '',
        }):
            creds = self.adapter.get_credentials()
            self.assertEqual(creds['phone_number_id'], '1298748379987770')
            self.assertEqual(creds['waba_id'], '1471882524763501')
            self.assertEqual(creds['env_phone_number_id'], '1171737406016871')
            self.assertEqual(creds['env_waba_id'], '1370721214882653')

        # 2. Without Meta token, unknown fields must report UNKNOWN (never FAILED or guessed)
        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': ''}), \
             patch.object(integrations_service.config, 'FB_ACCESS_TOKEN', None):
            status = integrations_service.get_whatsapp_integration_status(organization_id=1)

        self.assertTrue(status['success'])
        self.assertFalse(status['automatic_brand_binding'])
        self.assertEqual(status['verified_via'], 'no_token_unknown')
        self.assertEqual(status['preferred_phone_id'], '1298748379987770')
        self.assertEqual(status['preferred_waba_id'], '1471882524763501')
        self.assertEqual(status['configured_phone_id'], '1298748379987770')
        self.assertIn('reconciliation_summary', status['config_diagnosis'])

        accounts = status.get('accounts') or []
        self.assertEqual(len(accounts), 2)
        by_pid = {a['phone_number_id']: a for a in accounts}
        pref = by_pid['1298748379987770']
        sec = by_pid['1171737406016871']
        self.assertEqual(pref['waba_id'], '1471882524763501')
        self.assertEqual(sec['waba_id'], '1370721214882653')
        self.assertTrue(pref['is_preferred_candidate'])
        self.assertTrue(pref['offered_for_broadcast'])
        self.assertFalse(sec['offered_for_broadcast'])
        self.assertEqual(pref['platform_type'], 'UNKNOWN')
        self.assertEqual(pref['billing_readiness']['status'], 'UNKNOWN')
        self.assertIsNone(pref['brand_assignment'])
        self.assertIsNone(sec['brand_assignment'])

        # 3. Live Meta mock: CONNECTED + CLOUD_API must NEVER imply permission to send when BLOCKED/141006
        def _fake_get(url, **kwargs):
            m = MagicMock()
            if '/debug_token' in url:
                m.json.return_value = {'data': {'is_valid': True, 'expires_at': 0, 'scopes': ['whatsapp_business_management', 'whatsapp_business_messaging'], 'granular_scopes': []}}
            elif '/560075574375818' in url:
                m.json.return_value = {'id': '560075574375818', 'name': 'Aidni Global', 'verification_status': 'verified', 'owned_whatsapp_business_accounts': {'data': [{'id': '1471882524763501', 'name': 'Aidni Global'}]}}
            elif '/1298748379987770' in url:
                m.json.return_value = {
                    'id': '1298748379987770', 'display_phone_number': '+91 98257 28291', 'verified_name': 'Aidni Global',
                    'platform_type': 'CLOUD_API', 'status': 'CONNECTED', 'code_verification_status': 'NOT_VERIFIED',
                    'name_status': 'AVAILABLE_WITHOUT_REVIEW', 'health_status': {'can_send_message': 'BLOCKED', 'entities': [{'entity_type': 'WABA', 'id': '1471882524763501', 'can_send_message': 'BLOCKED', 'errors': [{'error_code': 141006, 'error_description': 'Payment error'}]}]},
                }
            elif '/1471882524763501/message_templates' in url or '/1370721214882653/message_templates' in url:
                m.json.return_value = {'data': []}
            elif '/1471882524763501/subscribed_apps' in url or '/1370721214882653/subscribed_apps' in url:
                m.json.return_value = {'data': []}
            elif '/1471882524763501' in url:
                m.json.return_value = {'error': {'code': 100, 'message': 'Authorization Error'}}
            else:
                m.json.return_value = {}
            return m

        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': 'tok_live'}), \
             patch.object(integrations_service.config, 'FB_ACCESS_TOKEN', 'tok_live'), \
             patch('requests.get', side_effect=_fake_get):
            live_st = integrations_service.get_whatsapp_integration_status(organization_id=1)

        live_pref = live_st['preferred_candidate']
        self.assertEqual(live_pref['phone_status'], 'CONNECTED')
        self.assertTrue(live_pref['connected_not_permitted'])
        self.assertEqual(live_pref['state_classification'], 'RESTRICTED')
        self.assertFalse(live_pref['messaging_eligibility']['eligible'])
        self.assertEqual(live_pref['billing_readiness']['status'], 'RESTRICTED')
        self.assertTrue(live_pref['billing_readiness']['has_payment_error'])
        self.assertTrue(live_pref['waba_association_verified'])

        # 4. Secondary number 1171737406016871 is NEVER offered for broadcasting or sandbox simulation
        ok_sec, _, err_sec = self.adapter.validate_sender('1171737406016871')
        self.assertFalse(ok_sec)
        self.assertIn('not offered for broadcasting', err_sec.lower())

        self._login()
        with patch.object(config, 'is_platform_publishing_enabled', return_value=False):
            r_def = self.client.post(
                '/api/whatsapp/simulate',
                json={'recipient_phone': '+91 98257 28291', 'template_name': 'client_welcome', 'message': 'Hi'},
                headers={'X-CSRFToken': 'test_csrf_token'},
            )
            self.assertEqual(r_def.status_code, 200)
            self.assertEqual(json.loads(r_def.data)['sender_phone_number_id'], '1298748379987770')

            r_sec = self.client.post(
                '/api/whatsapp/simulate',
                json={'recipient_phone': '+91 98257 28291', 'template_name': 'client_welcome', 'message': 'Hi', 'phone_number_id': '1171737406016871'},
                headers={'X-CSRFToken': 'test_csrf_token'},
            )
            self.assertEqual(r_sec.status_code, 400)
            self.assertIn('not offered for broadcasting', json.loads(r_sec.data)['error'].lower())

        # 5. UI checks: secondary not offered in simulator dropdown, cached/unknown/restricted states distinguished
        js_src = (Path(__file__).resolve().parent / 'static/script.js').read_text(encoding='utf-8')
        self.assertNotIn('Delivered (Simulated)', js_src)
        self.assertNotIn('id="wa-sender-select"', js_src)
        for token in ('1298748379987770', '1471882524763501', '1171737406016871', '1370721214882653', 'CONFIRMED LIVE', 'CACHED', 'UNKNOWN'):
            self.assertIn(token, js_src)


if __name__ == '__main__':
    unittest.main()

