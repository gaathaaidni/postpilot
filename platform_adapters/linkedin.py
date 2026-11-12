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
            'publishing_enabled': config.is_platform_publishing_enabled('linkedin')
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
        """Validates supported image media asset for LinkedIn REST Images API (JPG/JPEG/PNG/GIF)."""
        if not os.path.isfile(file_path):
            return {'success': False, 'error': f"Media file not found: {file_path}"}
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.gif'}:
            return {'success': False, 'error': f"Unsupported LinkedIn image format: '{ext}'. Supported formats: .jpg, .jpeg, .png, .gif."}
        return {'success': True, 'path': file_path, 'filename': os.path.basename(file_path)}

    def _upload_image_for_owner(self, owner_urn: str, media_ref: str, app_key: str, access_token: Optional[str], is_personal: bool) -> Tuple[bool, Optional[str], Optional[str]]:
        import config as app_config
        media_path = str(media_ref)
        if not os.path.isfile(media_path):
            candidate = os.path.join(str(app_config.UPLOAD_FOLDER), os.path.basename(media_path))
            if os.path.isfile(candidate):
                media_path = candidate

        ext = os.path.splitext(media_path)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.gif'}:
            return False, None, f"Unsupported LinkedIn media format '{ext}'. Supported image formats: JPG, JPEG, PNG, GIF."

        init_res = linkedin_api.initialize_image_upload(
            owner_urn,
            app_key=app_key,
            access_token=access_token,
            is_personal=is_personal,
        )
        if not init_res.get('success'):
            return False, None, init_res.get('error') or 'LinkedIn image upload initialization failed.'

        image_urn = init_res.get('image_urn')
        upload_url = init_res.get('upload_url')
        if not init_res.get('simulated'):
            if not os.path.isfile(media_path):
                return False, None, f"Media file not found for LinkedIn upload: {media_path}"
            if not upload_url:
                return False, None, "Failed uploading image binary to LinkedIn storage."
            ok_put = (
                linkedin_api.upload_image_file(upload_url, media_path, access_token=access_token)
                if access_token else
                linkedin_api.upload_image_file(upload_url, media_path)
            )
            if not ok_put:
                return False, None, "Failed uploading image binary to LinkedIn storage."
        return True, image_urn, None

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publishes explicitly either to a personal LinkedIn profile ('personal')
        OR to a verified LinkedIn company organization ('organization').
        Never silently redirects company <-> personal.
        """
        valid, err = self.validate_content(payload)
        if not valid:
            return {'success': False, 'platform': self.platform_key, 'error': err}

        text = payload.get('text') or payload.get('message') or payload.get('caption') or ''
        image_filename = payload.get('image_filename') or payload.get('media_filename')
        explicit_token = payload.get('access_token')
        dest_raw = str(payload.get('destination') or payload.get('linkedin_destination') or '').strip().lower()
        is_personal = (dest_raw == 'personal') or (str(payload.get('post_type') or '').strip().lower() == 'linkedin_personal')

        if image_filename:
            ext = os.path.splitext(str(image_filename).strip())[1].lower()
            if ext not in {'.jpg', '.jpeg', '.png', '.gif'}:
                return {
                    'success': False,
                    'platform': self.platform_key,
                    'destination': 'personal' if is_personal else 'organization',
                    'error': f"Unsupported LinkedIn media format '{ext}'. Supported image formats: JPG, JPEG, PNG, GIF.",
                }

        if is_personal:
            app_key = linkedin_api.normalize_app_key(payload.get('app_key') or linkedin_api.APP_AIDNI_GLOBAL)
            author_urn = payload.get('author_urn')
            image_urn = None

            if config.is_linkedin_personal_publishing_enabled():
                if not author_urn:
                    ident = linkedin_api.resolve_member_author(app_key, access_token=explicit_token, verify_live=True)
                    if not ident.get('success'):
                        return {
                            'success': False,
                            'platform': self.platform_key,
                            'destination': 'personal',
                            'app_key': app_key,
                            'error_code': ident.get('error_code'),
                            'error': ident.get('error') or 'Personal LinkedIn identity verification failed.',
                        }
                    author_urn = ident['author_urn']

            if image_filename:
                ok_up, image_urn, up_err = self._upload_image_for_owner(
                    author_urn or 'urn:li:person:simulated',
                    image_filename,
                    app_key=app_key,
                    access_token=explicit_token,
                    is_personal=True,
                )
                if not ok_up:
                    return {'success': False, 'platform': self.platform_key, 'destination': 'personal', 'error': up_err}

            res = linkedin_api.create_personal_post(
                text=text,
                app_key=app_key,
                access_token=explicit_token,
                image_urn=image_urn,
                author_urn=author_urn,
            )
            return {
                'success': res.get('success', False),
                'platform': self.platform_key,
                'destination': 'personal',
                'external_post_id': res.get('id') or res.get('share_urn'),
                'image_urn': image_urn,
                'app_key': app_key,
                'author_urn': res.get('author_urn') or author_urn,
                'simulated': res.get('simulated', False),
                'error_code': res.get('error_code'),
                'error': res.get('error'),
            }

        # Organization / Company Page path
        app_key = payload.get('app_key')
        acct = None
        if not app_key and payload.get('brand_id'):
            try:
                import database
                acct = database.get_social_account_for_brand(
                    payload.get('organization_id', 1),
                    payload['brand_id'],
                    'linkedin'
                )
                if acct and acct.get('app_identifier'):
                    app_key = acct['app_identifier']
                elif payload['brand_id'] == 1:
                    app_key = linkedin_api.APP_GAATHA_VENTURES
                else:
                    logger.warning(f"No LinkedIn account mapped for brand #{payload['brand_id']}. Cross-brand inheritance blocked.")
                    return {'success': False, 'platform': self.platform_key, 'destination': 'organization', 'error': f"No LinkedIn account mapped for brand #{payload['brand_id']}. Cross-brand inheritance blocked."}
            except Exception as ex:
                if payload['brand_id'] == 1:
                    app_key = linkedin_api.APP_GAATHA_VENTURES
                else:
                    logger.warning(f"No LinkedIn account mapped for brand #{payload['brand_id']} ({ex}). Cross-brand inheritance blocked.")
                    return {'success': False, 'platform': self.platform_key, 'destination': 'organization', 'error': f"No LinkedIn account mapped for brand #{payload['brand_id']}. Cross-brand inheritance blocked."}

        app_key = self.resolve_app_key(payload.get('linkedin_org_id'), app_key)
        app_cfg = linkedin_api.get_app_config(app_key)
        acct_org = acct.get('account_identifier') if acct else None
        org_id = payload.get('linkedin_org_id') or acct_org or app_cfg['org_id']

        if config.is_linkedin_company_publishing_enabled():
            elig = linkedin_api.check_organization_publishing_eligibility(app_key, access_token=explicit_token)
            if not elig.get('company_publishing_authorized'):
                return {
                    'success': False,
                    'platform': self.platform_key,
                    'destination': 'organization',
                    'app_key': app_key,
                    'organization_id': org_id,
                    'error_code': elig.get('eligibility_code', 'COMMUNITY_MANAGEMENT_API_REQUIRED'),
                    'error': elig.get('eligibility_message') or 'Company-page publishing is not authorized on LinkedIn.',
                }

        image_urn = None
        if image_filename:
            ok_up, image_urn, up_err = self._upload_image_for_owner(
                str(org_id),
                image_filename,
                app_key=app_key,
                access_token=explicit_token,
                is_personal=False,
            )
            if not ok_up:
                return {'success': False, 'platform': self.platform_key, 'destination': 'organization', 'error': up_err}

        res = linkedin_api.create_organization_post(
            organization_id=org_id,
            text=text,
            app_key=app_key,
            access_token=explicit_token,
            image_urn=image_urn
        )

        return {
            'success': res.get('success', True),
            'platform': self.platform_key,
            'destination': 'organization',
            'external_post_id': res.get('id') or res.get('share_urn'),
            'image_urn': image_urn,
            'app_key': app_key,
            'organization_id': org_id,
            'simulated': res.get('simulated', False),
            'error_code': res.get('error_code'),
            'error': res.get('error')
        }

    def classify_error(self, error: Any) -> Dict[str, Any]:
        """Classifies LinkedIn API errors into standardized categories."""
        err_str = str(error)
        err_code = 'PLATFORM_ERROR'
        is_retryable = False

        if '401' in err_str or 'token' in err_str.lower() or 'expired' in err_str.lower():
            err_code = 'TOKEN_EXPIRED'
        elif '403' in err_str or 'w_organization_social' in err_str.lower():
            err_code = 'CM_API_REQUIRED'
        elif '3000' in err_str or 'validation' in err_str.lower():
            err_code = 'INVALID_PAYLOAD'
        elif 'timeout' in err_str.lower() or '500' in err_str:
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
        """Returns composite status of both LinkedIn applications."""
        return linkedin_api.audit_linkedin_status()
