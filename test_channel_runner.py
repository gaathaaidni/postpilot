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
        self.assertTrue(callable(nexora_suite.run_nexora_suite))
        self.assertTrue(callable(nexora_suite.stop_nexora_suite))

        # 2. nexora_by_phoenix_international
        self.assertEqual(nexora_by_phoenix_international.POST_TYPE, 'nz')
        self.assertEqual(nexora_by_phoenix_international.PAGE_ID, config.FB_PAGE_ID_PHOENIX)
        self.assertTrue(callable(nexora_by_phoenix_international.run_nexora_by_phoenix))
        self.assertTrue(callable(nexora_by_phoenix_international.stop_nexora_by_phoenix))

        # 3. gaatha_loop
        self.assertEqual(gaatha_loop.POST_TYPE, 'gaatha')
        self.assertEqual(gaatha_loop.PAGE_ID, config.FB_PAGE_ID_GAATHA_AI)
        self.assertTrue(callable(gaatha_loop.run_gaatha_loop))
        self.assertTrue(callable(gaatha_loop.stop_gaatha_loop))
        self.assertTrue(callable(gaatha_loop.post_to_facebook))

    def test_zero_secrets_in_channel_metadata(self):
        """Ensures channel metadata never stores or leaks access tokens."""
        for ch in channel_runner.CHANNELS.values():
            self.assertFalse(hasattr(ch, 'access_token'))
            self.assertFalse(hasattr(ch, 'token'))

if __name__ == "__main__":
    unittest.main()
