"""
PostPilot Instagram Platform Adapter
Encapsulates Instagram Professional account publishing via Meta Instagram Graph API.
Strictly respects POSTPILOT_PUBLISHING_ENABLED=0 safety guardrail.
"""
import os
import time
import logging
from typing import Dict, Any, Optional, Tuple

import config
import facebook_api
import insta
from platform_adapters.base import BasePlatformAdapter

logger = logging.getLogger(__name__)


class InstagramAdapter(BasePlatformAdapter):
    """Adapter for Instagram Business & Creator account publishing."""

    def __init__(self):
        super().__init__(platform_key='instagram', display_name='Instagram Professional')

    def get_configured_accounts(self) -> Dict[str, Dict[str, Any]]:
        """Returns map of configured Instagram Professional accounts."""
        accounts = {}
        if config.INSTA_ID_SUITE:
            accounts['suite'] = {
                'ig_user_id': str(config.INSTA_ID_SUITE),
                'username': '@nexora_suite',
                'linked_page_id': config.FB_PAGE_ID_SUITE
            }
        if config.INSTA_ID_PHOENIX:
            accounts['phoenix'] = {
                'ig_user_id': str(config.INSTA_ID_PHOENIX),
                'username': '@phoenixbygaatha',
                'linked_page_id': config.FB_PAGE_ID_PHOENIX
            }
        return accounts

    def resolve_ig_user_id(self, target_identifier: Optional[str] = None) -> Optional[str]:
        """Resolves target IG User ID from key or direct numeric ID."""
        if not target_identifier:
            return config.INSTA_ID_PHOENIX or config.INSTA_ID_SUITE

        clean = str(target_identifier).strip()
        accounts = self.get_configured_accounts()
        if clean in accounts:
            return accounts[clean]['ig_user_id']
        if clean.isdigit():
            return clean
        return config.INSTA_ID_PHOENIX

    def validate_connection(self, ig_user_id: Optional[str] = None) -> Dict[str, Any]:
        """Validates configuration and token presence without making external requests."""
        token_configured = bool(config.FB_ACCESS_TOKEN and config.FB_ACCESS_TOKEN.strip())
        target_ig = self.resolve_ig_user_id(ig_user_id)
        accounts = self.get_configured_accounts()

        return {
            'platform': self.platform_key,
            'configured': token_configured and bool(target_ig),
            'token_configured': token_configured,
            'active_ig_user_id': target_ig,
            'accounts_count': len(accounts),
            'publishing_enabled': config.is_publishing_enabled()
        }

    def validate_content(self, content: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validates Instagram content:
        Instagram strictly mandates media (image or video). Text-only posts are not permitted.
        Max caption length: 2,200 characters. Max hashtags: 30.
        """
        image_url = content.get('image_url')
        image_filename = content.get('image_filename') or content.get('media_filename')
        has_media = bool((image_url and str(image_url).strip()) or (image_filename and str(image_filename).strip()))

        if not has_media:
            return False, "Instagram requires an image or video attachment. Text-only posts are not supported."

        caption = content.get('caption') or content.get('message') or ''
        if len(str(caption)) > 2200:
            return False, f"Instagram caption exceeds 2,200 character limit ({len(str(caption))} chars)."

        hashtags = [w for w in str(caption).split() if w.startswith('#')]
        if len(hashtags) > 30:
            return False, f"Instagram post exceeds maximum of 30 hashtags (found {len(hashtags)})."

        return True, None

    def upload_media(self, file_path: str, media_type: str = 'image', **kwargs) -> Dict[str, Any]:
        """Validates media file for Instagram container compatibility."""
        if not os.path.isfile(file_path):
            return {'success': False, 'error': f"Media file not found: {file_path}"}
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.mp4', '.mov'}:
            return {'success': False, 'error': f"Unsupported Instagram media format: '{ext}'."}
        return {'success': True, 'path': file_path, 'filename': os.path.basename(file_path)}

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publishes content to Instagram.
        When POSTPILOT_PUBLISHING_ENABLED=0, intercepts and returns simulated result.
        """
        valid, err = self.validate_content(payload)
        if not valid:
            return {'success': False, 'platform': self.platform_key, 'error': err}

        ig_user_id = self.resolve_ig_user_id(payload.get('ig_user_id') or payload.get('channel_key'))
        if not ig_user_id:
            return {'success': False, 'platform': self.platform_key, 'error': 'No Instagram User ID resolved.'}

        caption = payload.get('caption') or payload.get('message') or ''
        image_url = payload.get('image_url')

        # Safety Guardrail: Intercept when publishing is disabled
        if not config.is_publishing_enabled():
            sim_id = f"ig_media_sim_{int(time.time() * 1000)}"
            logger.info(
                f"🛡️ [SAFETY] Instagram publishing simulated (POSTPILOT_PUBLISHING_ENABLED=0): "
                f"User {ig_user_id}, caption preview='{caption[:40]}...'"
            )
            return {
                'success': True,
                'platform': self.platform_key,
                'external_post_id': sim_id,
                'ig_user_id': ig_user_id,
                'simulated': True,
                'message': 'Simulated publishing: POSTPILOT_PUBLISHING_ENABLED is 0'
            }

        # Real publish via insta module
        token = facebook_api.get_access_token()
        success = insta.post_to_instagram(
            image_url=image_url,
            caption=caption,
            ig_user_id=ig_user_id,
            access_token=token
        )

        if not success:
            return {'success': False, 'platform': self.platform_key, 'error': 'Instagram container publishing failed.'}

        return {
            'success': True,
            'platform': self.platform_key,
            'external_post_id': f"ig_{int(time.time())}",
            'ig_user_id': ig_user_id,
            'simulated': False
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns structured health of Instagram adapter."""
        conn = self.validate_connection()
        return {
            'platform': self.platform_key,
            'display_name': self.display_name,
            'configured': conn['configured'],
            'publishing_enabled': config.is_publishing_enabled(),
            'accounts': self.get_configured_accounts()
        }
