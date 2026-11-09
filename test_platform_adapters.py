"""
test_platform_adapters.py - Unified Platform Adapters Test Suite
Validates:
1. PlatformRegistry initialization and adapter discovery
2. Canonical platform resolution (Facebook, Instagram, LinkedIn, WhatsApp)
3. Legacy channel mapping ('tour', 'nz', 'gaatha', 'insta')
4. Content validation and constraint checks per platform
5. Strict publishing safety guardrail (POSTPILOT_PUBLISHING_ENABLED=0)
6. WhatsApp phone normalization, template verification, and webhook HMAC
"""
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
from platform_adapters import (
    PlatformRegistry,
    BasePlatformAdapter,
    BaseMessagingAdapter,
    FacebookAdapter,
    InstagramAdapter,
    LinkedInAdapter,
    WhatsAppCloudAdapter,
    CANONICAL_PLATFORMS,
    LEGACY_CHANNELS
)


class TestPlatformAdapters(unittest.TestCase):

    def setUp(self):
        # Enforce publishing disabled guardrail
        config.POSTPILOT_PUBLISHING_ENABLED = False

    def test_01_registry_canonical_resolution(self):
        """Verifies registry correctly resolves all canonical platform adapters."""
        fb = PlatformRegistry.get_adapter('facebook')
        self.assertIsInstance(fb, FacebookAdapter)
        self.assertEqual(fb.platform_key, 'facebook')

        ig = PlatformRegistry.get_adapter('instagram')
        self.assertIsInstance(ig, InstagramAdapter)
        self.assertEqual(ig.platform_key, 'instagram')

        li = PlatformRegistry.get_adapter('linkedin')
        self.assertIsInstance(li, LinkedInAdapter)
        self.assertEqual(li.platform_key, 'linkedin')

        wa = PlatformRegistry.get_adapter('whatsapp')
        self.assertIsInstance(wa, WhatsAppCloudAdapter)
        self.assertEqual(wa.platform_key, 'whatsapp')

    def test_02_registry_legacy_channel_mapping(self):
        """Verifies legacy channels ('tour', 'nz', 'gaatha', 'insta') map to appropriate adapters."""
        tour = PlatformRegistry.get_adapter('tour')
        self.assertIsInstance(tour, FacebookAdapter)

        nz = PlatformRegistry.get_adapter('nz')
        self.assertIsInstance(nz, FacebookAdapter)

        gaatha = PlatformRegistry.get_adapter('gaatha')
        self.assertIsInstance(gaatha, FacebookAdapter)

        insta = PlatformRegistry.get_adapter('insta')
        self.assertIsInstance(insta, InstagramAdapter)

        self.assertTrue(PlatformRegistry.is_legacy_channel('tour'))
        self.assertTrue(PlatformRegistry.is_legacy_channel('nz'))
        self.assertTrue(PlatformRegistry.is_legacy_channel('gaatha'))
        self.assertTrue(PlatformRegistry.is_legacy_channel('insta'))
        self.assertFalse(PlatformRegistry.is_legacy_channel('facebook'))

    def test_03_metadata_listing(self):
        """Verifies platform registry metadata returns structured info for all platforms."""
        platforms = PlatformRegistry.list_supported_platforms()
        keys = {p['key'] for p in platforms}
        self.assertEqual(keys, {'facebook', 'instagram', 'linkedin', 'whatsapp'})

    def test_04_facebook_adapter_content_validation(self):
        """Verifies Facebook adapter content validation and constraints."""
        adapter = FacebookAdapter()

        # Valid text post
        valid, err = adapter.validate_content({'message': 'Hello world'})
        self.assertTrue(valid)
        self.assertIsNone(err)

        # Empty content
        valid, err = adapter.validate_content({'message': '', 'image_filename': ''})
        self.assertFalse(valid)
        self.assertIn('empty', err.lower())

        # Exceeds character limit
        long_msg = 'a' * 65000
        valid, err = adapter.validate_content({'message': long_msg})
        self.assertFalse(valid)
        self.assertIn('character limit', err.lower())

    def test_05_instagram_adapter_content_validation(self):
        """Verifies Instagram content validation requires media and enforces limits."""
        adapter = InstagramAdapter()

        # Text-only post must fail (Instagram requires media)
        valid, err = adapter.validate_content({'message': 'Text only'})
        self.assertFalse(valid)
        self.assertIn('image or video', err.lower())

        # Exceeds 30 hashtags
        hashtags_msg = 'Post ' + ' '.join([f'#tag{i}' for i in range(35)])
        valid, err = adapter.validate_content({'message': hashtags_msg, 'image_filename': 'photo.jpg'})
        self.assertFalse(valid)
        self.assertIn('hashtag', err.lower())

        # Valid post with image
        valid, err = adapter.validate_content({'message': 'Great photo! #social', 'image_filename': 'photo.jpg'})
        self.assertTrue(valid)

    def test_06_linkedin_adapter_content_validation(self):
        """Verifies LinkedIn content validation and character limits."""
        adapter = LinkedInAdapter()

        # Valid post
        valid, err = adapter.validate_content({'message': 'Company announcement'})
        self.assertTrue(valid)

        # Exceeds 3000 character commentary limit
        long_msg = 'x' * 3100
        valid, err = adapter.validate_content({'message': long_msg})
        self.assertFalse(valid)
        self.assertTrue('3,000' in err or '3000' in err)

    def test_07_whatsapp_adapter_phone_and_templates(self):
        """Verifies WhatsApp phone normalization and template validation."""
        adapter = WhatsAppCloudAdapter()

        # Phone normalization via validate_phone_number
        valid, norm = adapter.validate_phone_number('+1 (555) 234-5678')
        self.assertTrue(valid)
        self.assertEqual(norm, '+15552345678')

        valid, norm = adapter.validate_phone_number('+91 98765-43210')
        self.assertTrue(valid)
        self.assertEqual(norm, '+919876543210')

        # Invalid phone
        valid, err = adapter.validate_phone_number('123')
        self.assertFalse(valid)

        # Template listing
        templates = adapter.get_templates()
        self.assertTrue(len(templates) >= 2)
        template_names = [t['name'] for t in templates]
        self.assertIn('client_welcome', template_names)
        self.assertIn('campaign_announcement', template_names)

    def test_08_whatsapp_webhook_signature_verification(self):
        """Verifies WhatsApp HMAC SHA-256 webhook signature validation."""
        adapter = WhatsAppCloudAdapter()
        secret = "test_webhook_app_secret_123"

        import hmac
        import hashlib
        payload = b'{"object": "whatsapp_business_account"}'
        sig = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        header = f"sha256={sig}"

        self.assertTrue(adapter.verify_webhook_signature(payload, header, app_secret=secret))
        self.assertFalse(adapter.verify_webhook_signature(payload, "sha256=invalid_signature", app_secret=secret))

    def test_09_safety_guardrail_publishing_blocked(self):
        """Verifies that publish calls across all adapters respect POSTPILOT_PUBLISHING_ENABLED=0."""
        # Facebook simulation
        fb_res = PlatformRegistry.dispatch({'post_type': 'facebook', 'message': 'Safety test'})
        self.assertTrue(fb_res['success'])
        self.assertTrue(fb_res.get('simulated'))

        # Instagram simulation
        ig_res = PlatformRegistry.dispatch({'post_type': 'instagram', 'message': 'Safety test', 'image_filename': 'test.jpg'})
        self.assertTrue(ig_res['success'])
        self.assertTrue(ig_res.get('simulated'))

        # LinkedIn simulation
        li_res = PlatformRegistry.dispatch({'post_type': 'linkedin', 'message': 'Safety test'})
        self.assertTrue(li_res['success'])
        self.assertTrue(li_res.get('simulated'))

        # WhatsApp simulation
        wa = PlatformRegistry.get_adapter('whatsapp')
        wa_res = wa.send_template('+15552345678', 'client_welcome')
        self.assertTrue(wa_res['success'])
        self.assertTrue(wa_res.get('simulated'))


if __name__ == '__main__':
    unittest.main()
