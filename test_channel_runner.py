"""
test_channel_runner.py - Validation for PostPilot Channel Runner Architecture
Verifies:
1. Channel registry initialization and configuration loading
2. Dynamic Page ID resolution and configuration fallbacks
3. Post type mapping and delegation to posting_utils.load_posts
4. Dispatch and posting delegation to posting_utils.post_on_facebook
5. Background loop execution delegation and graceful stop_event signaling
6. Backward compatibility wrappers (nexora_suite, nexora_by_phoenix_international, gaatha_loop)
7. Zero credential leakage across channel metadata
"""
import os
import sys
import unittest
import requests
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import channel_runner
import posting_utils
import facebook_api
import nexora_suite
import nexora_by_phoenix_international
import gaatha_loop


class TestChannelRunner(unittest.TestCase):

    def test_channel_registry(self):
        """Verifies canonical channels ('tour', 'nz', 'gaatha') are registered."""
        channels = channel_runner.list_channels()
        keys = [c['key'] for c in channels]
        self.assertIn('tour', keys)
        self.assertIn('nz', keys)
        self.assertIn('gaatha', keys)
        self.assertEqual(len(keys), 3)

        # Keys map to expected post_types
        self.assertEqual(channel_runner.get_channel('tour').post_type, 'tour')
        self.assertEqual(channel_runner.get_channel('nz').post_type, 'nz')
        self.assertEqual(channel_runner.get_channel('gaatha').post_type, 'gaatha')

    def test_invalid_channel_lookup(self):
        """Verifies error raised on unknown channel lookup."""
        with self.assertRaises(KeyError):
            channel_runner.get_channel('unknown_channel')

    def test_page_id_resolution(self):
        """Tests that environment overrides configuration default safely."""
        ch = channel_runner.get_channel('tour')
        # Default
        self.assertEqual(ch.get_page_id(), config.FB_PAGE_ID_SUITE)

        # Environment override
        with patch.dict(os.environ, {'FB_PAGE_ID_SUITE': '1122334455'}):
            self.assertEqual(ch.get_page_id(), '1122334455')

    def test_interval_and_callback_management(self):
        """Tests interval setting and callback assignment."""
        ch = channel_runner.get_channel('tour')
        ch.set_interval(999)
        self.assertEqual(ch.current_interval, 999)

        mock_cb = MagicMock()
        ch.set_status_callback(mock_cb)
        self.assertEqual(ch.status_callback, mock_cb)

    @patch('posting_utils.load_posts')
    def test_load_posts_delegation(self, mock_load):
        """Tests load_posts delegates to posting_utils with correct post_type."""
        mock_load.return_value = [{'id': 1, 'message': 'Sample'}]
        ch = channel_runner.get_channel('nz')
        posts = ch.load_posts()
        mock_load.assert_called_once_with('nz')
        self.assertEqual(len(posts), 1)

    @patch('facebook_api.get_access_token')
    @patch('posting_utils.post_on_facebook')
    def test_post_on_facebook_delegation(self, mock_post, mock_token):
        """Tests post_on_facebook dispatches with resolved page_id and token."""
        mock_token.return_value = 'MOCK_TOKEN'
        mock_post.return_value = {'photo_id': '12345'}

        ch = channel_runner.get_channel('gaatha')
        result = ch.post_on_facebook('Hello World', 'test.jpg')

        mock_post.assert_called_once_with(
            'Hello World',
            'test.jpg',
            ch.get_page_id(),
            'MOCK_TOKEN',
            ig_user_id=None,
            channel_key='gaatha'
        )
        self.assertEqual(result, {'photo_id': '12345'})

    @patch('facebook_api.get_access_token')
    @patch('posting_utils.run_posting_loop')
    def test_run_and_stop_signals(self, mock_loop, mock_token):
        """Tests run delegates to posting_utils and stop sets stop_event."""
        mock_token.return_value = 'MOCK_TOKEN'
        ch = channel_runner.get_channel('tour')
        ch.stop_event.clear()
        self.assertFalse(ch.stop_event.is_set())

        ch.run()
        mock_loop.assert_called_once()
        self.assertEqual(mock_loop.call_args[1]['callback_key'], 'tour')
        self.assertEqual(mock_loop.call_args[1]['channel_key'], 'tour')
        self.assertEqual(mock_loop.call_args[1]['post_type'], 'tour')

        ch.stop()
        self.assertTrue(ch.stop_event.is_set())

    def test_backward_compatibility_wrappers(self):
        """Verifies nexora_suite, nexora_by_phoenix_international, and gaatha_loop wrap correctly."""
        # 1. nexora_suite
        self.assertEqual(nexora_suite.POST_TYPE, 'tour')
        self.assertEqual(nexora_suite.PAGE_ID, config.FB_PAGE_ID_SUITE)
        self.assertIsInstance(nexora_suite.current_interval, int)
        self.assertTrue(callable(nexora_suite.run_nexora_suite))
        self.assertTrue(callable(nexora_suite.stop_nexora_suite))

        # 2. nexora_by_phoenix_international
        self.assertEqual(nexora_by_phoenix_international.POST_TYPE, 'nz')
        self.assertEqual(nexora_by_phoenix_international.PAGE_ID, config.FB_PAGE_ID_PHOENIX)
        self.assertIsInstance(nexora_by_phoenix_international.current_interval, int)
        self.assertTrue(callable(nexora_by_phoenix_international.run_nexora_by_phoenix))
        self.assertTrue(callable(nexora_by_phoenix_international.stop_nexora_by_phoenix))

        # 3. gaatha_loop
        self.assertEqual(gaatha_loop.POST_TYPE, 'gaatha')
        self.assertEqual(gaatha_loop.PAGE_ID, config.FB_PAGE_ID_GAATHA_AI)
        self.assertIsInstance(gaatha_loop.current_interval, int)
        self.assertTrue(callable(gaatha_loop.run_gaatha_loop))
        self.assertTrue(callable(gaatha_loop.stop_gaatha_loop))
        self.assertTrue(callable(gaatha_loop.post_to_facebook))

    def test_dynamic_module_attributes_via_getattr(self):
        """Tests that module __getattr__ correctly resolves dynamic PAGE_ID and current_interval."""
        with patch.dict(os.environ, {'FB_PAGE_ID_SUITE': '999888777666'}):
            self.assertEqual(nexora_suite.PAGE_ID, '999888777666')
        with patch.dict(os.environ, {'FB_PAGE_ID_PHOENIX': '888777666555'}):
            self.assertEqual(nexora_by_phoenix_international.PAGE_ID, '888777666555')
        with patch.dict(os.environ, {'FB_PAGE_ID_GAATHA_AI': '777666555444'}):
            self.assertEqual(gaatha_loop.PAGE_ID, '777666555444')

    def test_all_channel_aliases_resolution(self):
        """Verifies all supported environment variable aliases resolve predictably for each channel."""
        tour_ch = channel_runner.get_channel('tour')
        nz_ch = channel_runner.get_channel('nz')
        gaatha_ch = channel_runner.get_channel('gaatha')

        # tour aliases
        with patch.dict(os.environ, {'TOUR_PAGE_ID': '1010101010'}):
            with patch.dict(os.environ, {'FB_PAGE_ID_SUITE': '', 'FB_PAGE_ID_NEXORA_SUITE': ''}):
                self.assertEqual(tour_ch.get_page_id(), '1010101010')

        # nz aliases
        with patch.dict(os.environ, {'VISA_PAGE_ID': '2020202020'}):
            with patch.dict(os.environ, {'FB_PAGE_ID_PHOENIX': '', 'FB_PAGE_ID_NEXORA_BY_PHOENIX': ''}):
                self.assertEqual(nz_ch.get_page_id(), '2020202020')

        # gaatha aliases
        with patch.dict(os.environ, {'FB_PAGE_ID_GAATHA': '3030303030'}):
            with patch.dict(os.environ, {'FB_PAGE_ID_GAATHA_AI': ''}):
                self.assertEqual(gaatha_ch.get_page_id(), '3030303030')

    def test_invalid_page_id_rejection(self):
        """Ensures non-numeric and empty Page IDs fail clearly with ValueError."""
        ch = channel_runner.get_channel('tour')
        with patch.dict(os.environ, {'FB_PAGE_ID_SUITE': 'not_a_valid_id'}):
            with self.assertRaises(ValueError) as ctx:
                ch.get_page_id()
            self.assertIn("Page IDs must consist of numeric digits", str(ctx.exception))

        custom_ch = channel_runner.Channel('custom', 'Custom', 'custom', ('CUSTOM_PAGE_ID',), '', 1800)
        with patch.dict(os.environ, {'CUSTOM_PAGE_ID': ''}):
            with self.assertRaises(ValueError) as ctx:
                custom_ch.get_page_id()
            self.assertIn("Missing Facebook Page ID configuration", str(ctx.exception))

    def test_cross_channel_collision_detection(self):
        """Verifies validate_channel_routing detects and rejects accidental duplicate mappings."""
        # 1. Standard channels should pass validation with unique IDs
        mapping = channel_runner.validate_channel_routing()
        self.assertEqual(len(mapping), 3)
        self.assertEqual(len(set(mapping.values())), 3)

        # 2. Collision simulated: nz accidentally set to tour's Page ID
        tour_id = channel_runner.get_channel('tour').get_page_id()
        with patch.dict(os.environ, {'FB_PAGE_ID_PHOENIX': tour_id}):
            with self.assertRaises(ValueError) as ctx:
                channel_runner.validate_channel_routing()
            self.assertIn("Cross-channel routing conflict", str(ctx.exception))

    @patch('facebook_api.get_page_token')
    @patch('facebook_api._request_with_retry')
    def test_text_only_post_payload_construction(self, mock_req, mock_token):
        """Verifies text-only posts route to /{page_id}/feed instead of failing on missing image."""
        mock_token.return_value = 'MOCK_PAGE_TOKEN'
        mock_req.return_value = {'id': 'feed_post_12345'}

        res = posting_utils.post_on_facebook(
            message="Text only announcement",
            image_filename="",
            page_id="967550829768297",
            access_token="MOCK_USER_TOKEN"
        )
        self.assertTrue(res)
        self.assertEqual(res['id'], 'feed_post_12345')

        # Check call arguments
        call_args = mock_req.call_args
        self.assertEqual(call_args[0][0], "POST")
        self.assertIn("/feed", call_args[0][1])
        self.assertEqual(call_args[1]['data']['message'], "Text only announcement")
        self.assertEqual(call_args[1]['data']['access_token'], "MOCK_PAGE_TOKEN")

    def test_channel_isolated_instagram_binding(self):
        """Ensures Instagram IDs are channel-specific and unconfigured channels don't cross-post."""
        tour_ch = channel_runner.get_channel('tour')
        nz_ch = channel_runner.get_channel('nz')
        gaatha_ch = channel_runner.get_channel('gaatha')

        self.assertEqual(tour_ch.get_insta_id(), config.INSTA_ID_SUITE)
        self.assertEqual(nz_ch.get_insta_id(), config.INSTA_ID_PHOENIX)
        self.assertIsNone(gaatha_ch.get_insta_id())

    def test_channel_specific_token_resolution(self):
        """Verifies channel-specific token resolution and precedence over global tokens."""
        tour_ch = channel_runner.get_channel('tour')
        nz_ch = channel_runner.get_channel('nz')
        gaatha_ch = channel_runner.get_channel('gaatha')

        # 1. Channel-specific overrides take precedence
        with patch.dict(os.environ, {
            'FB_PAGE_TOKEN_TOUR': 'TOUR_SPECIFIC_TOKEN',
            'FB_ACCESS_TOKEN_NZ': 'NZ_SPECIFIC_TOKEN',
            'FB_PAGE_TOKEN_GAATHA': 'GAATHA_SPECIFIC_TOKEN',
            'FB_ACCESS_TOKEN': 'GLOBAL_FALLBACK_TOKEN'
        }):
            self.assertEqual(tour_ch.get_access_token(), 'TOUR_SPECIFIC_TOKEN')
            self.assertEqual(nz_ch.get_access_token(), 'NZ_SPECIFIC_TOKEN')
            self.assertEqual(gaatha_ch.get_access_token(), 'GAATHA_SPECIFIC_TOKEN')

        # 2. Page-ID-specific token override
        with patch.dict(os.environ, {
            'FB_PAGE_TOKEN_TOUR': '',
            'FB_PAGE_TOKEN_SUITE': '',
            'FB_ACCESS_TOKEN_TOUR': '',
            f'FB_PAGE_TOKEN_{tour_ch.get_page_id()}': 'PID_SPECIFIC_TOKEN',
            'FB_ACCESS_TOKEN': 'GLOBAL_FALLBACK_TOKEN'
        }):
            self.assertEqual(tour_ch.get_access_token(), 'PID_SPECIFIC_TOKEN')

        # 3. Falls back to global when no channel token is set
        with patch.dict(os.environ, {
            'FB_PAGE_TOKEN_TOUR': '',
            'FB_PAGE_TOKEN_SUITE': '',
            'FB_ACCESS_TOKEN_TOUR': '',
            f'FB_PAGE_TOKEN_{tour_ch.get_page_id()}': '',
            'FB_ACCESS_TOKEN': 'GLOBAL_TOKEN_123'
        }):
            self.assertEqual(tour_ch.get_access_token(), 'GLOBAL_TOKEN_123')

    @patch('requests.get')
    def test_page_token_direct_match(self, mock_get):
        """Verifies that if user_token is already a Page Access Token, it returns directly via /me."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'id': '967550829768297', 'name': 'Gaatha Suite'}
        mock_get.return_value = mock_resp

        tok = facebook_api.get_page_token(user_token='DIRECT_PAGE_TOKEN', page_id='967550829768297')
        self.assertEqual(tok, 'DIRECT_PAGE_TOKEN')
        # Only /me should have been queried, not /me/accounts
        self.assertEqual(mock_get.call_count, 1)
        self.assertIn('/me', mock_get.call_args[0][0])

    @patch('requests.get')
    def test_page_token_exchange_via_accounts(self, mock_get):
        """Verifies user access token is exchanged for page token via /me/accounts."""
        # Call 1: /me returns user profile (different ID)
        me_resp = MagicMock()
        me_resp.json.return_value = {'id': '10998877665544', 'name': 'Admin User'}
        # Call 2: /me/accounts returns list of pages
        accounts_resp = MagicMock()
        accounts_resp.json.return_value = {
            'data': [
                {'id': '954901604381882', 'name': 'Nexora Phoenix', 'access_token': 'RESOLVED_PHOENIX_PAGE_TOKEN'},
                {'id': '967550829768297', 'name': 'Nexora Suite', 'access_token': 'RESOLVED_SUITE_PAGE_TOKEN'}
            ]
        }
        mock_get.side_effect = [me_resp, accounts_resp]

        tok = facebook_api.get_page_token(user_token='USER_TOKEN_123', page_id='954901604381882')
        self.assertEqual(tok, 'RESOLVED_PHOENIX_PAGE_TOKEN')

    @patch('requests.get')
    def test_page_token_direct_node_fallback(self, mock_get):
        """Verifies direct /{page_id} lookup when page is missing from /me/accounts."""
        me_resp = MagicMock()
        me_resp.json.return_value = {'id': '10998877665544', 'name': 'Admin User'}
        accounts_resp = MagicMock()
        accounts_resp.json.return_value = {'data': []}
        page_resp = MagicMock()
        page_resp.json.return_value = {'id': '1028368893692590', 'name': 'Gaatha AI', 'access_token': 'DIRECT_NODE_PAGE_TOKEN'}
        mock_get.side_effect = [me_resp, accounts_resp, page_resp]

        tok = facebook_api.get_page_token(user_token='USER_TOKEN_123', page_id='1028368893692590')
        self.assertEqual(tok, 'DIRECT_NODE_PAGE_TOKEN')

    def test_error_classification_all_categories(self):
        """Verifies Facebook API error classification for all expected error codes."""
        # Auth errors
        for code in (102, 190, 463, 467):
            self.assertEqual(facebook_api.classify_facebook_error({'error': {'code': code}}), 'AUTH_ERROR')

        # Permission errors
        for code in (10, 200, 283):
            self.assertEqual(facebook_api.classify_facebook_error({'error': {'code': code}}), 'PERMISSION_ERROR')

        # Duplicate post
        self.assertEqual(facebook_api.classify_facebook_error({'error': {'code': 506}}), 'DUPLICATE_POST')

        # Rate limits
        for code in (4, 17, 32, 613):
            self.assertEqual(facebook_api.classify_facebook_error({'error': {'code': code}}), 'RATE_LIMIT')
        self.assertEqual(facebook_api.classify_facebook_error({}, status_code=429), 'RATE_LIMIT')

        # Server errors
        for code in (1, 2):
            self.assertEqual(facebook_api.classify_facebook_error({'error': {'code': code}}), 'SERVER_ERROR')
        for status in (500, 502, 503, 504):
            self.assertEqual(facebook_api.classify_facebook_error({}, status_code=status), 'SERVER_ERROR')

        # Client errors
        for code in (100, 368):
            self.assertEqual(facebook_api.classify_facebook_error({'error': {'code': code}}), 'CLIENT_ERROR')

    @patch('facebook_api.get_token_info')
    def test_audit_publishing_capabilities(self, mock_info):
        """Verifies audit_publishing_capabilities returns expected capability breakdown."""
        mock_info.return_value = {
            'is_valid': True,
            'type': 'PAGE',
            'expires_at': 0,
            'profile_id': '967550829768297',
            'scopes': ['pages_manage_posts', 'pages_read_engagement', 'pages_show_list', 'publish_video', 'instagram_content_publish']
        }

        audit = facebook_api.audit_publishing_capabilities('SAMPLE_PAGE_TOKEN', page_id='967550829768297')
        self.assertTrue(audit['valid'])
        self.assertTrue(audit['expires_never'])
        self.assertTrue(audit['matches_page'])
        self.assertTrue(audit['can_publish_facebook'])
        self.assertTrue(audit['can_publish_video'])
        self.assertTrue(audit['can_publish_instagram'])
        self.assertEqual(len(audit['missing_permissions']), 0)

    def test_payload_validation_empty_text_post(self):
        """Verifies text posts with whitespace/empty content fail pre-flight validation immediately."""
        res_empty = posting_utils.post_on_facebook(
            message="   ",
            image_filename="",
            page_id="967550829768297",
            access_token="MOCK_TOKEN"
        )
        self.assertFalse(res_empty)

        res_none = posting_utils.post_on_facebook(
            message=None,
            image_filename="",
            page_id="967550829768297",
            access_token="MOCK_TOKEN"
        )
        self.assertFalse(res_none)

    @patch('insta.post_to_instagram')
    @patch('facebook_api._request_with_retry')
    @patch('facebook_api.get_page_token')
    def test_instagram_photo_url_retrieval_uses_params_not_url(self, mock_get_token, mock_req, mock_insta):
        """
        Verifies that photo URL retrieval for Instagram cross-posting passes the access token
        in params, never embedded in the URL string.
        """
        mock_get_token.return_value = 'MOCK_PAGE_TOKEN_SECURE'
        mock_insta.return_value = True

        # First call: Photo upload response; Second call: Photo details response
        mock_req.side_effect = [
            {'id': 'photo_123456789'},
            {'images': [{'source': 'https://fbcdn.net/sample_photo.jpg'}]}
        ]

        # Create temporary dummy file in upload folder
        dummy_file = 'sec_test_photo.png'
        dummy_path = os.path.join(str(config.UPLOAD_FOLDER), dummy_file)
        os.makedirs(os.path.dirname(dummy_path), exist_ok=True)
        with open(dummy_path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01')

        try:
            res = posting_utils.post_on_facebook(
                message="Testing secure photo URL retrieval",
                image_filename=dummy_file,
                page_id="967550829768297",
                access_token="MOCK_USER_TOKEN",
                ig_user_id="17841449080283492"
            )
            self.assertTrue(res)
            self.assertEqual(res['photo_id'], 'photo_123456789')
            self.assertEqual(res['image_url'], 'https://fbcdn.net/sample_photo.jpg')

            # Verify the second _request_with_retry call (GET photo details)
            self.assertEqual(mock_req.call_count, 2)
            photo_details_call = mock_req.call_args_list[1]
            method = photo_details_call[0][0]
            url = photo_details_call[0][1]
            kwargs = photo_details_call[1]

            self.assertEqual(method, "GET")
            # CRITICAL SECURITY ASSERTION: URL MUST NOT embed access_token
            self.assertNotIn("access_token", url)
            self.assertNotIn("MOCK_PAGE_TOKEN_SECURE", url)
            self.assertEqual(url, f"{facebook_api.BASE_URL}/photo_123456789")

            # CRITICAL SECURITY ASSERTION: Access token passed in params dictionary
            self.assertIn("params", kwargs)
            self.assertEqual(kwargs['params']['fields'], 'images')
            self.assertEqual(kwargs['params']['access_token'], 'MOCK_PAGE_TOKEN_SECURE')
        finally:
            if os.path.exists(dummy_path):
                os.remove(dummy_path)

    def test_sanitize_log_message_redacts_credentials(self):
        """Verifies sanitize_log_message redacts access tokens and parameters in all formats."""
        # 1. URL query parameters
        url_with_token = "https://graph.facebook.com/v19.0/12345?fields=images&access_token=EAATsecretTokenValue1234567890"
        sanitized = facebook_api.sanitize_log_message(url_with_token)
        self.assertNotIn("EAATsecretTokenValue1234567890", sanitized)
        self.assertIn("access_token=[REDACTED]", sanitized)

        # 2. Key-value string representation
        kv_with_token = "Payload sent: {'access_token': 'EAATsecretTokenValue1234567890', 'caption': 'Hello'}"
        sanitized_kv = facebook_api.sanitize_log_message(kv_with_token)
        self.assertNotIn("EAATsecretTokenValue1234567890", sanitized_kv)
        self.assertIn("'access_token': '[REDACTED]'", sanitized_kv)

        # 3. Meta error message with raw token
        err_with_token = "Invalid OAuth access token EAATsuperSecretToken1234567890"
        sanitized_err = facebook_api.sanitize_log_message(err_with_token)
        self.assertNotIn("EAATsuperSecretToken1234567890", sanitized_err)
        self.assertIn("[REDACTED_TOKEN]", sanitized_err)

        # 4. Safe strings remain intact
        safe_msg = "Successfully published post 12345 to page 967550829768297"
        self.assertEqual(facebook_api.sanitize_log_message(safe_msg), safe_msg)

    @patch('posting_utils.logger.error')
    @patch('facebook_api.get_page_token')
    def test_exception_logging_does_not_leak_token(self, mock_token, mock_log_err):
        """Verifies that exceptions in posting_utils sanitize log messages and do not leak tokens."""
        mock_token.side_effect = Exception("Failed connecting with access_token=EAATleakedSecret1234567890")

        res = posting_utils.post_on_facebook(
            message="Test message",
            image_filename="",
            page_id="967550829768297",
            access_token="MOCK_TOKEN"
        )
        self.assertFalse(res)

        mock_log_err.assert_called_once()
        logged_msg = mock_log_err.call_args[0][0]
        self.assertNotIn("EAATleakedSecret1234567890", logged_msg)
        self.assertTrue("[REDACTED" in logged_msg)

    @patch('time.sleep')
    @patch('facebook_api.logger.warning')
    @patch('requests.request')
    def test_request_with_retry_exception_sanitizes_logs(self, mock_request, mock_log_warn, mock_sleep):
        """Verifies that network exceptions in _request_with_retry never log tokens."""
        mock_request.side_effect = requests.exceptions.ConnectionError(
            "Connection failed for url: https://graph.facebook.com/?access_token=EAATsecretNetworkToken12345"
        )

        facebook_api._request_with_retry("GET", "https://graph.facebook.com/v19.0/12345")
        self.assertTrue(mock_log_warn.called)
        for call in mock_log_warn.call_args_list:
            msg = call[0][0]
            self.assertNotIn("EAATsecretNetworkToken12345", msg)
            self.assertTrue("[REDACTED" in msg)

    def test_zero_secrets_in_channel_metadata(self):
        """Ensures channel metadata never stores or leaks access tokens."""
        for ch in channel_runner.CHANNELS.values():
            self.assertFalse(hasattr(ch, 'access_token'))
            self.assertFalse(hasattr(ch, 'token'))

if __name__ == "__main__":
    unittest.main()
