"""
PostPilot Instagram Platform Adapter
Encapsulates Instagram Professional account publishing via Meta Instagram Graph API v19.0.
Implements the full two-phase container creation, status polling, and publication lifecycle.
Strictly respects POSTPILOT_PUBLISHING_ENABLED=0 safety guardrail.
"""
import os
import time
import logging
from typing import Dict, Any, Optional, Tuple
import requests

import config
import facebook_api
from platform_adapters.base import BasePlatformAdapter

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
SUPPORTED_PHOTO_FORMATS = {'.jpg', '.jpeg', '.png'}
SUPPORTED_VIDEO_FORMATS = {'.mp4', '.mov'}


class InstagramAdapter(BasePlatformAdapter):
    """Adapter for Instagram Business & Creator account publishing."""

    def __init__(self):
        super().__init__(platform_key='instagram', display_name='Instagram Professional')

    def get_configured_accounts(self) -> Dict[str, Dict[str, Any]]:
        """Returns map of configured Instagram Professional accounts from config and synced INSTA_ID_* env vars."""
        accounts = {}
        known_defs = [
            ('phoenix', 'INSTA_ID_PHOENIX', '@phoenixbygaatha', getattr(config, 'INSTA_ID_PHOENIX', '17841471822022390'), os.getenv('FB_PAGE_ID_PHOENIX') or getattr(config, 'FB_PAGE_ID_PHOENIX', '954901604381882')),
            ('suite', 'INSTA_ID_SUITE', '@gaathasuite', getattr(config, 'INSTA_ID_SUITE', '17841449080283492'), os.getenv('FB_PAGE_ID_SUITE') or getattr(config, 'FB_PAGE_ID_SUITE', '967550829768297')),
            ('grahak_chetna', 'INSTA_ID_GRAHAK_CHETNA', '@grahak.chetna', getattr(config, 'INSTA_ID_GRAHAK_CHETNA', '17841467723671727'), os.getenv('FB_PAGE_ID_GRAHAK_CHETNA') or getattr(config, 'FB_PAGE_ID_GRAHAK_CHETNA', '374211199112915')),
        ]
        for key, env_key, username, cfg_val, linked_pid in known_defs:
            val = os.getenv(env_key) or cfg_val
            if val and str(val).strip():
                accounts[key] = {
                    'ig_user_id': str(val).strip(),
                    'username': username,
                    'linked_page_id': linked_pid,
                    'env_key': env_key
                }

        for env_key, env_val in sorted(os.environ.items()):
            if env_key.startswith('INSTA_ID_') and env_val and str(env_val).strip():
                slug = env_key[len('INSTA_ID_'):].lower()
                if slug and slug not in accounts:
                    accounts[slug] = {
                        'ig_user_id': str(env_val).strip(),
                        'username': f"@{slug}",
                        'linked_page_id': os.getenv(f"FB_PAGE_ID_{slug.upper()}"),
                        'env_key': env_key
                    }
        return accounts

    def get_linked_facebook_page_id(self, ig_user_id: Optional[str]) -> Optional[str]:
        """Returns the verified linked Facebook Page ID for a configured Instagram account."""
        target = str(ig_user_id or '').strip()
        if not target:
            return None
        for info in self.get_configured_accounts().values():
            if info.get('ig_user_id') == target and info.get('linked_page_id'):
                return str(info['linked_page_id'])
        verified = getattr(config, 'VERIFIED_META_INSTAGRAM_ACCOUNTS', {})
        if target in verified:
            return verified[target].get('facebook_page_id')
        return None

    def get_account_for_facebook_page(self, page_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Returns Instagram account metadata linked to a given Facebook Page ID."""
        target_pid = str(page_id or '').strip()
        if not target_pid:
            return None
        for key, info in self.get_configured_accounts().items():
            if str(info.get('linked_page_id') or '').strip() == target_pid:
                return {'key': key, **info}
        return None

    def resolve_ig_user_id(
        self,
        target_identifier: Optional[str] = None,
        brand_id: Optional[int] = None,
        organization_id: int = 1
    ) -> Optional[str]:
        """Resolves target IG User ID from brand ownership, key, or direct numeric ID."""
        # 1. Brand-specific lookup from social_accounts table
        if brand_id:
            try:
                import database
                acct = database.get_social_account_for_brand(organization_id, brand_id, 'instagram')
                if acct and acct.get('account_identifier'):
                    return str(acct['account_identifier'])
            except Exception:
                pass
            if brand_id == 5:
                return str(config.INSTA_ID_PHOENIX)
            elif brand_id == 1:
                return str(config.INSTA_ID_SUITE)
            # Specific brand requested but no Instagram account mapped: strictly block cross-brand inheritance
            logger.warning(f"No Instagram account mapped for brand #{brand_id}. Cross-brand inheritance blocked.")
            return None

        # 2. Key or numeric identifier lookup
        if target_identifier:
            clean = str(target_identifier).strip()
            accounts = self.get_configured_accounts()
            if clean in accounts:
                return accounts[clean]['ig_user_id']
            if clean.isdigit():
                return clean

        return str(config.INSTA_ID_PHOENIX or config.INSTA_ID_SUITE)

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
            'publishing_enabled': config.is_platform_publishing_enabled('instagram')
        }

    def verify_public_media_url(self, url: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Verifies that media URL is a valid, publicly accessible HTTP or HTTPS URL."""
        if not url or not str(url).strip():
            return False, "Instagram media attachment requires a valid media URL or file."
        clean = str(url).strip().lower()
        if not (clean.startswith('http://') or clean.startswith('https://')):
            return False, "Instagram API requires an accessible public HTTP/HTTPS URL for media assets."
        
        from urllib.parse import urlparse
        parsed = urlparse(clean)
        hostname = (parsed.hostname or '').lower()
        if hostname in ('localhost', '127.0.0.1', '::1') or hostname.startswith('192.168.') or hostname.startswith('10.') or hostname.startswith('172.'):
            return False, f"Instagram API cannot access local or private host: {hostname}. URL must be publicly reachable."
        return True, None

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

    def create_container(
        self,
        ig_user_id: str,
        media_url: str,
        caption: str = "",
        is_video: bool = False,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Step 1: Creates an Instagram media container.
        POST /{ig-user-id}/media
        """
        if not config.is_platform_publishing_enabled('instagram'):
            sim_container_id = f"ig_container_sim_{int(time.time() * 1000)}"
            return {'success': True, 'container_id': sim_container_id, 'simulated': True}

        token = access_token or facebook_api.get_access_token()
        url = f"{GRAPH_BASE_URL}/{ig_user_id}/media"
        params = {
            'access_token': token,
            'caption': caption
        }
        if is_video:
            params['video_url'] = media_url
            params['media_type'] = 'REELS'
        else:
            params['image_url'] = media_url

        try:
            res = requests.post(url, data=params, timeout=30)
            data = res.json()
            if res.status_code == 200 and 'id' in data:
                return {'success': True, 'container_id': data['id'], 'simulated': False}
            err_msg = data.get('error', {}).get('message', res.text)
            return {'success': False, 'error': err_msg, 'response': data}
        except Exception as e:
            return {'success': False, 'error': facebook_api.sanitize_log_message(str(e))}

    def poll_container_status(
        self,
        container_id: str,
        access_token: Optional[str] = None,
        max_polls: int = 5,
        poll_interval: float = 1.0
    ) -> Tuple[bool, str]:
        """
        Step 2: Polls container processing status until FINISHED or ERROR.
        GET /{container-id}?fields=status_code,status
        """
        if not config.is_platform_publishing_enabled('instagram') or container_id.startswith('ig_container_sim_'):
            return True, 'FINISHED'

        token = access_token or facebook_api.get_access_token()
        url = f"{GRAPH_BASE_URL}/{container_id}"
        params = {'fields': 'status_code,status', 'access_token': token}

        for attempt in range(max_polls):
            try:
                res = requests.get(url, params=params, timeout=15)
                data = res.json()
                status = data.get('status_code') or data.get('status', 'IN_PROGRESS')
                if status == 'FINISHED':
                    return True, 'FINISHED'
                elif status in ('ERROR', 'EXPIRED'):
                    return False, f"Container processing failed with status: {status}"
                time.sleep(poll_interval)
            except Exception as e:
                logger.warning(f"Error polling container {container_id}: {facebook_api.sanitize_log_message(str(e))}")
                time.sleep(poll_interval)

        return False, "Container processing timed out waiting for FINISHED status."

    def publish_container(
        self,
        ig_user_id: str,
        container_id: str,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Step 3: Publishes an approved, finished container to Instagram.
        POST /{ig-user-id}/media_publish
        """
        if not config.is_platform_publishing_enabled('instagram') or container_id.startswith('ig_container_sim_'):
            sim_media_id = f"ig_media_sim_{int(time.time() * 1000)}"
            return {'success': True, 'media_id': sim_media_id, 'simulated': True}

        token = access_token or facebook_api.get_access_token()
        url = f"{GRAPH_BASE_URL}/{ig_user_id}/media_publish"
        params = {
            'creation_id': container_id,
            'access_token': token
        }

        try:
            res = requests.post(url, data=params, timeout=30)
            data = res.json()
            if res.status_code == 200 and 'id' in data:
                return {'success': True, 'media_id': data['id'], 'simulated': False}
            err_msg = data.get('error', {}).get('message', res.text)
            return {'success': False, 'error': err_msg, 'response': data}
        except Exception as e:
            return {'success': False, 'error': facebook_api.sanitize_log_message(str(e))}

    def upload_media(self, file_path: str, media_type: str = 'image', **kwargs) -> Dict[str, Any]:
        """Validates media file for Instagram container compatibility."""
        if not os.path.isfile(file_path):
            return {'success': False, 'error': f"Media file not found: {file_path}"}
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_PHOTO_FORMATS and ext not in SUPPORTED_VIDEO_FORMATS:
            return {'success': False, 'error': f"Unsupported Instagram media format: '{ext}'."}
        return {'success': True, 'path': file_path, 'filename': os.path.basename(file_path)}

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coordinates full Instagram publishing:
        1. Content & hashtag validation
        2. Account resolution (brand-specific)
        3. Media container creation
        4. Processing status polling
        5. Container publication
        When POSTPILOT_PUBLISHING_ENABLED=0, safely intercepts and returns simulated result.
        """
        valid, err = self.validate_content(payload)
        if not valid:
            return {'success': False, 'platform': self.platform_key, 'error': err}

        ig_user_id = self.resolve_ig_user_id(
            target_identifier=payload.get('ig_user_id') or payload.get('channel_key'),
            brand_id=payload.get('brand_id'),
            organization_id=payload.get('organization_id', 1)
        )
        if not ig_user_id:
            return {'success': False, 'platform': self.platform_key, 'error': 'No Instagram User ID resolved for brand.'}

        caption = payload.get('caption') or payload.get('message') or ''
        image_url = payload.get('image_url') or payload.get('media_url')
        if not image_url:
            # Fall back to public host URL using filename if configured
            filename = payload.get('image_filename') or payload.get('media_filename')
            base_url = getattr(config, 'PUBLIC_MEDIA_BASE_URL', None) or 'https://postpilot.gaatha.tech/images'
            image_url = f"{base_url}/{filename}" if filename else None

        # Safety Guardrail: Intercept when publishing is disabled
        if not config.is_platform_publishing_enabled('instagram'):
            sim_container_id = f"ig_container_sim_{int(time.time() * 1000)}"
            sim_id = f"ig_media_sim_{int(time.time() * 1000)}"
            logger.info(
                f"🛡️ [SAFETY] Instagram publishing simulated (POSTPILOT_PUBLISHING_ENABLED=0): "
                f"User {ig_user_id}, caption preview='{caption[:40]}...'"
            )
            return {
                'success': True,
                'platform': self.platform_key,
                'external_post_id': sim_id,
                'container_id': sim_container_id,
                'ig_user_id': ig_user_id,
                'simulated': True,
                'message': 'Simulated publishing: POSTPILOT_PUBLISHING_ENABLED is 0'
            }

        # Step 1: Create Container
        container_res = self.create_container(ig_user_id, image_url, caption=caption)
        if not container_res.get('success'):
            return {'success': False, 'platform': self.platform_key, 'error': container_res.get('error')}
        container_id = container_res['container_id']

        # Step 2: Poll Processing Status
        ready, status_msg = self.poll_container_status(container_id)
        if not ready:
            return {'success': False, 'platform': self.platform_key, 'error': status_msg}

        # Step 3: Publish Container
        pub_res = self.publish_container(ig_user_id, container_id)
        if not pub_res.get('success'):
            return {'success': False, 'platform': self.platform_key, 'error': pub_res.get('error')}

        media_id = pub_res['media_id']
        return {
            'success': True,
            'platform': self.platform_key,
            'external_post_id': media_id,
            'container_id': container_id,
            'ig_user_id': ig_user_id,
            'simulated': False
        }

    def classify_error(self, error: Any) -> Dict[str, Any]:
        """Classifies Instagram Graph API errors into standardized categories."""
        err_str = str(error)
        err_code = 'PLATFORM_ERROR'
        is_retryable = False

        if '190' in err_str or 'token' in err_str.lower() or 'expired' in err_str.lower():
            err_code = 'TOKEN_EXPIRED'
        elif 'container' in err_str.lower():
            err_code = 'CONTAINER_FAILED'
        elif 'rate limit' in err_str.lower() or ' 32' in err_str or ': 32' in err_str:
            err_code = 'RATE_LIMITED'
            is_retryable = True
        elif 'aspect ratio' in err_str.lower() or 'format' in err_str.lower() or '100' in err_str:
            err_code = 'INVALID_MEDIA'
        elif 'timeout' in err_str.lower() or 'transient' in err_str.lower():
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
        """Returns structured health of Instagram adapter."""
        conn = self.validate_connection()
        return {
            'platform': self.platform_key,
            'display_name': self.display_name,
            'configured': conn['configured'],
            'publishing_enabled': config.is_platform_publishing_enabled('instagram'),
            'accounts': self.get_configured_accounts()
        }
