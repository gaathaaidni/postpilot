"""
PostPilot Facebook Platform Adapter
Encapsulates Facebook Page publishing (Feed text, Photos, Videos) via Meta Graph API.
Strictly respects POSTPILOT_PUBLISHING_ENABLED=0 safety guardrail.
"""
import os
import time
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

import config
import facebook_api
import posting_utils
from platform_adapters.base import BasePlatformAdapter

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}


class FacebookAdapter(BasePlatformAdapter):
    """Adapter for Facebook Page management and publishing."""

    def __init__(self):
        super().__init__(platform_key='facebook', display_name='Facebook Pages')

    def get_configured_pages(self) -> Dict[str, Dict[str, Any]]:
        """Returns map of configured Facebook Pages from environment/config."""
        pages = {}
        if config.FB_PAGE_ID_SUITE:
            pages['suite'] = {
                'page_id': str(config.FB_PAGE_ID_SUITE),
                'name': 'Nexora Suite',
                'env_key': 'FB_PAGE_ID_SUITE'
            }
        if config.FB_PAGE_ID_PHOENIX:
            pages['phoenix'] = {
                'page_id': str(config.FB_PAGE_ID_PHOENIX),
                'name': 'Phoenix International',
                'env_key': 'FB_PAGE_ID_PHOENIX'
            }
        if getattr(config, 'FB_PAGE_ID_GAATHA_AI', None):
            pages['gaatha_ai'] = {
                'page_id': str(config.FB_PAGE_ID_GAATHA_AI),
                'name': 'Gaatha AI',
                'env_key': 'FB_PAGE_ID_GAATHA_AI'
            }
        return pages

    def resolve_page_id(self, target_identifier: Optional[str] = None, brand_id: Optional[int] = None, organization_id: int = 1) -> Optional[str]:
        """Resolves target page ID based on brand assignment or explicit identifier."""
        # 1. Brand-specific resolution from database or config mapping
        if brand_id:
            try:
                import database
                acct = database.get_social_account_for_brand(organization_id, brand_id, 'facebook')
                if acct and acct.get('account_identifier'):
                    return str(acct['account_identifier'])
            except Exception:
                pass
            if brand_id == 5:
                return str(config.FB_PAGE_ID_PHOENIX)
            elif brand_id == 1:
                return str(config.FB_PAGE_ID_SUITE)
            elif brand_id == 6 and getattr(config, 'FB_PAGE_ID_GAATHA_AI', None):
                return str(config.FB_PAGE_ID_GAATHA_AI)

        # 2. Key or explicit identifier lookup
        if target_identifier:
            clean = str(target_identifier).strip()
            pages = self.get_configured_pages()
            if clean in pages:
                return pages[clean]['page_id']
            if clean:
                return clean

        return str(config.FB_PAGE_ID_SUITE or config.FB_PAGE_ID_PHOENIX)

    def validate_connection(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """Validates configuration and token presence without making external requests."""
        token_configured = bool(config.FB_ACCESS_TOKEN and config.FB_ACCESS_TOKEN.strip())
        target_pid = self.resolve_page_id(page_id)
        pages = self.get_configured_pages()

        return {
            'platform': self.platform_key,
            'configured': token_configured and bool(target_pid),
            'token_configured': token_configured,
            'active_page_id': target_pid,
            'pages_count': len(pages),
            'publishing_enabled': config.is_publishing_enabled()
        }

    def validate_content(self, content: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates Facebook post content."""
        message = content.get('message') or content.get('caption') or ''
        image_filename = content.get('image_filename') or content.get('media_filename')

        has_media = bool(image_filename and str(image_filename).strip())
        if not has_media and (not message or not str(message).strip()):
            return False, "Facebook text posts require non-empty text content."

        if len(str(message)) > 63206:
            return False, "Facebook post message exceeds 63,206 character limit."

        if has_media:
            ext = os.path.splitext(str(image_filename).strip())[1].lower()
            if ext not in PHOTO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
                return False, f"Unsupported Facebook media format: '{ext}'."

        return True, None

    def upload_media(self, file_path: str, media_type: str = 'image', **kwargs) -> Dict[str, Any]:
        """Validates local media file existence and format."""
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return {'success': False, 'error': f"Media file not found: {file_path}"}
        ext = p.suffix.lower()
        if ext not in PHOTO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
            return {'success': False, 'error': f"Unsupported media extension: {ext}"}
        return {'success': True, 'path': str(p), 'filename': p.name, 'size': p.stat().st_size}

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publishes content to Facebook Page.
        When POSTPILOT_PUBLISHING_ENABLED=0, intercepts and returns simulated result.
        """
        valid, err = self.validate_content(payload)
        if not valid:
            return {'success': False, 'platform': self.platform_key, 'error': err}

        page_id = self.resolve_page_id(
            target_identifier=payload.get('page_id') or payload.get('channel_key'),
            brand_id=payload.get('brand_id'),
            organization_id=payload.get('organization_id', 1)
        )
        if not page_id:
            return {'success': False, 'platform': self.platform_key, 'error': 'No Facebook Page ID resolved for target brand.'}

        message = payload.get('message') or payload.get('caption') or ''
        image_filename = payload.get('image_filename') or payload.get('media_filename')

        # Safety Guardrail: Intercept when publishing is disabled
        if not config.is_publishing_enabled():
            sim_id = f"fb_post_sim_{int(time.time() * 1000)}"
            logger.info(
                f"🛡️ [SAFETY] Facebook publishing simulated (POSTPILOT_PUBLISHING_ENABLED=0): "
                f"Page {page_id}, text preview='{message[:40]}...'"
            )
            return {
                'success': True,
                'platform': self.platform_key,
                'external_post_id': sim_id,
                'page_id': page_id,
                'simulated': True,
                'message': 'Simulated publishing: POSTPILOT_PUBLISHING_ENABLED is 0'
            }

        # Real publish via posting_utils
        token = facebook_api.get_access_token()
        res = posting_utils.post_on_facebook(
            message=message,
            image_filename=image_filename,
            page_id=page_id,
            access_token=token
        )

        if not res:
            return {'success': False, 'platform': self.platform_key, 'error': 'Facebook publishing failed.'}

        ext_id = res.get('photo_id') or res.get('id')
        return {
            'success': True,
            'platform': self.platform_key,
            'external_post_id': ext_id,
            'page_id': page_id,
            'simulated': False,
            'response': res
        }

    def classify_error(self, error: Any) -> Dict[str, Any]:
        """Classifies Meta Graph API errors into standardized categories."""
        err_str = str(error)
        err_code = 'PLATFORM_ERROR'
        is_retryable = False

        if '190' in err_str or 'token' in err_str.lower() or 'expired' in err_str.lower():
            err_code = 'TOKEN_EXPIRED'
        elif '100' in err_str or 'param' in err_str.lower() or 'invalid' in err_str.lower():
            err_code = 'INVALID_PARAMETER'
        elif '200' in err_str or 'permission' in err_str.lower():
            err_code = 'PERMISSION_DENIED'
        elif 'transient' in err_str.lower() or 'timeout' in err_str.lower() or '500' in err_str:
            err_code = 'TRANSIENT_ERROR'
            is_retryable = True

        return {
            'success': False,
            'platform': self.platform_key,
            'error_code': err_code,
            'error_message': err_str,
            'retryable': is_retryable
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns structured health of Facebook adapter."""
        conn = self.validate_connection()
        return {
            'platform': self.platform_key,
            'display_name': self.display_name,
            'configured': conn['configured'],
            'publishing_enabled': config.is_publishing_enabled(),
            'pages': self.get_configured_pages()
        }
