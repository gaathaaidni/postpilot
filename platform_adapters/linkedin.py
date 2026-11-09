"""
PostPilot LinkedIn Platform Adapter
Encapsulates LinkedIn Organization publishing via modern REST Posts API (202401).
Supports dual-application architecture: Aidni Global LLP and Gaatha Ventures Sh.p.k.
Strictly respects POSTPILOT_PUBLISHING_ENABLED=0 safety guardrail.
"""
import os
import time
import logging
from typing import Dict, Any, Optional, Tuple

import config
import linkedin_api
from platform_adapters.base import BasePlatformAdapter

logger = logging.getLogger(__name__)


class LinkedInAdapter(BasePlatformAdapter):
    """Adapter for LinkedIn Organization Pages publishing and token management."""

    def __init__(self):
        super().__init__(platform_key='linkedin', display_name='LinkedIn Organization')

    def get_configured_apps(self) -> Dict[str, Dict[str, Any]]:
        """Returns map of configured LinkedIn applications."""
        return {
            linkedin_api.APP_AIDNI_GLOBAL: {
                'app_key': linkedin_api.APP_AIDNI_GLOBAL,
                'display_name': 'Aidni Global LLP',
                'org_id': linkedin_api.DEFAULT_ORG_ID_AIDNI_GLOBAL,
                'configured': bool(config.LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP and config.LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP)
            },
            linkedin_api.APP_GAATHA_VENTURES: {
                'app_key': linkedin_api.APP_GAATHA_VENTURES,
                'display_name': 'Gaatha Ventures Sh.p.k.',
                'org_id': linkedin_api.DEFAULT_ORG_ID_GAATHA_VENTURES,
                'configured': bool(config.LINKEDIN_CLIENT_ID_GAATHA_VENTURES and config.LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES)
            }
        }

    def resolve_app_key(self, organization_id: Optional[str] = None, app_key: Optional[str] = None) -> str:
        """Resolves LinkedIn app key from explicit parameter or target organization ID."""
        if app_key:
            return linkedin_api.normalize_app_key(app_key)
        if organization_id:
            clean = str(organization_id).replace("urn:li:organization:", "").strip()
            if clean == linkedin_api.DEFAULT_ORG_ID_AIDNI_GLOBAL:
                return linkedin_api.APP_AIDNI_GLOBAL
        return linkedin_api.APP_GAATHA_VENTURES

    def validate_connection(self, app_key: Optional[str] = None) -> Dict[str, Any]:
        """Checks configuration and OAuth authentication status."""
        target_app = self.resolve_app_key(app_key=app_key)
        app_cfg = linkedin_api.get_app_config(target_app)
        token_data = linkedin_api.get_token_data(target_app)
        is_authed = bool(token_data and not linkedin_api.is_token_expired(token_data))

        return {
            'platform': self.platform_key,
            'app_key': target_app,
            'configured': app_cfg['configured'],
            'authenticated': is_authed,
            'token_expired': linkedin_api.is_token_expired(token_data) if token_data else True,
            'org_id': app_cfg['org_id'],
            'publishing_enabled': config.is_publishing_enabled()
        }

    def validate_content(self, content: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validates LinkedIn post content.
        Text posts require non-empty commentary (max 3,000 characters).
        """
        text = content.get('text') or content.get('message') or content.get('caption') or ''
        if not text or not str(text).strip():
            return False, "LinkedIn posts require non-empty text content."

        if len(str(text)) > 3000:
            return False, f"LinkedIn post exceeds 3,000 character limit ({len(str(text))} chars)."

        return True, None

    def upload_media(self, file_path: str, media_type: str = 'image', **kwargs) -> Dict[str, Any]:
        """Validates media asset for LinkedIn."""
        if not os.path.isfile(file_path):
            return {'success': False, 'error': f"Media file not found: {file_path}"}
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.gif', '.mp4'}:
            return {'success': False, 'error': f"Unsupported LinkedIn media format: '{ext}'."}
        return {'success': True, 'path': file_path, 'filename': os.path.basename(file_path)}

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publishes an organization update to LinkedIn.
        When POSTPILOT_PUBLISHING_ENABLED=0, intercepts and returns simulated result.
        """
        valid, err = self.validate_content(payload)
        if not valid:
            return {'success': False, 'platform': self.platform_key, 'error': err}

        text = payload.get('text') or payload.get('message') or payload.get('caption') or ''
        app_key = self.resolve_app_key(payload.get('organization_id'), payload.get('app_key'))
        app_cfg = linkedin_api.get_app_config(app_key)
        org_id = payload.get('organization_id') or app_cfg['org_id']

        # Delegate to linkedin_api.create_organization_post (handles safe mode internally)
        res = linkedin_api.create_organization_post(
            organization_id=org_id,
            text=text,
            app_key=app_key
        )

        return {
            'success': res.get('success', True),
            'platform': self.platform_key,
            'external_post_id': res.get('id') or res.get('share_urn'),
            'app_key': app_key,
            'organization_id': org_id,
            'simulated': res.get('simulated', False),
            'error': res.get('error')
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns composite status of both LinkedIn applications."""
        return linkedin_api.audit_linkedin_status()
