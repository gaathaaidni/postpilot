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
            'MOCK_TOKEN'
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

    def test_zero_secrets_in_channel_metadata(self):
        """Ensures channel metadata never stores or leaks access tokens."""
        for ch in channel_runner.CHANNELS.values():
            self.assertFalse(hasattr(ch, 'access_token'))
            self.assertFalse(hasattr(ch, 'token'))

if __name__ == "__main__":
    unittest.main()
