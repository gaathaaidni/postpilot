"""
PostPilot WhatsApp Business Platform Adapter
Implements Meta WhatsApp Business Cloud API integration for broadcast marketing.
Supports local template preview separation, E.164 phone normalization,
template variable validation, sender/brand isolation, error classification,
token health checks, and delivery webhook signature verification.
Strictly respects WHATSAPP_PUBLISHING_ENABLED=0 safety guardrail.
"""
import os
import re
import time
import hmac
import hashlib
import logging
import requests
from typing import Dict, Any, Optional, Tuple, List

import config
import facebook_api
from platform_adapters.base import BaseMessagingAdapter

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"
WHATSAPP_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Preserved WABA / Phone assets (never removed, reassigned, migrated, or auto-bound to brands)
PREFERRED_PHONE_NUMBER_ID = "1298748379987770"
PREFERRED_WABA_ID = "1471882524763501"
LEGACY_DISCONNECTED_PHONE_NUMBER_ID = "1171737406016871"
LEGACY_DISCONNECTED_WABA_ID = "1370721214882653"

DEFAULT_WABA_ID = LEGACY_DISCONNECTED_WABA_ID
DEFAULT_PHONE_NUMBER = "+919825728291"

PRESERVED_WHATSAPP_NUMBERS = {
    "1298748379987770": {
        "phone_number_id": "1298748379987770",
        "waba_id": "1471882524763501",
        "display_phone_number": "+91 98257 28291",
        "business_name": "Aidni Global",
        "role": "preferred_sender",
        "is_preferred_candidate": True,
        "offered_for_broadcast": True,
        "is_disconnected_legacy": False,
        "notes": "Only preferred PostPilot WhatsApp sender under verified Business Portfolio 560075574375818 (Aidni Global). Connected does NOT mean permitted; sending remains restricted pending verification, billing, templates, and webhooks.",
    },
    "1171737406016871": {
        "phone_number_id": "1171737406016871",
        "waba_id": "1370721214882653",
        "display_phone_number": "+91 90990 28291",
        "business_name": "Gaatha Ventures",
        "role": "preserved_secondary",
        "is_preferred_candidate": False,
        "offered_for_broadcast": False,
        "is_disconnected_legacy": True,
        "notes": "Preserved secondary account (.env legacy reference). Not deleted or migrated, and NEVER offered for broadcasting.",
    },
}

WHATSAPP_ERROR_CLASSIFICATIONS = {
    190: ("AUTH_EXPIRED", "Access token expired or invalid. Re-authenticate Meta token."),
    10: ("PERMISSION_ERROR", "Missing WhatsApp Business Management/Messaging API permission."),
    200: ("PERMISSION_ERROR", "Insufficient permissions for target WhatsApp Business Asset."),
    130429: ("RATE_LIMIT", "WhatsApp Cloud API throughput limit exceeded. Retry with backoff."),
    80007: ("RATE_LIMIT", "WABA rate limit hit. Retry later."),
    131026: ("RECIPIENT_ERROR", "Recipient phone number is not on WhatsApp or cannot receive message."),
    131047: ("RE_ENGAGEMENT_REQUIRED", "More than 24 hours passed since last user reply; an approved template is required."),
    132000: ("TEMPLATE_PARAM_ERROR", "Number of template parameters does not match Meta template definition."),
    132001: ("TEMPLATE_NOT_FOUND", "Template does not exist or is not approved on this WABA."),
    132012: ("TEMPLATE_FORMAT_ERROR", "Template parameter format mismatch."),
    141006: ("PAYMENT_METHOD_REQUIRED", "WABA payment method missing or invalid; business-initiated messaging is blocked."),
    141007: ("TIMEZONE_REQUIRED", "WABA timezone must be configured before sending messages."),
    141010: ("BUSINESS_VERIFICATION_REQUIRED", "Owning Meta Business Portfolio must complete verification."),
}


class WhatsAppCloudAdapter(BaseMessagingAdapter):
    """Adapter for official Meta WhatsApp Business Cloud API broadcasts."""

    def __init__(self):
        super().__init__(platform_key='whatsapp', display_name='WhatsApp Business Cloud')
        self._templates_cache: List[Dict[str, Any]] = []

    def get_credentials(self) -> Dict[str, Any]:
        """Resolves WhatsApp credentials and dual-account metadata without exposing secrets."""
        wa_tok = (os.getenv('WHATSAPP_ACCESS_TOKEN') or '').strip()
        fb_tok = (getattr(config, 'FB_ACCESS_TOKEN', None) or os.getenv('FB_ACCESS_TOKEN') or '').strip()
        token = wa_tok or fb_tok or None
        token_source = 'WHATSAPP_ACCESS_TOKEN' if wa_tok else ('FB_ACCESS_TOKEN' if fb_tok else 'NONE')

        active_override = (os.getenv('WHATSAPP_ACTIVE_PHONE_NUMBER_ID') or '').strip()
        configured_phone_id = (os.getenv('WHATSAPP_PHONE_NUMBER_ID') or '').strip()
        # +91 98257 28291 (1298748379987770) is the ONLY preferred PostPilot sender; preserve .env 1171737406016871 untouched without selecting it for broadcast
        phone_id = active_override or PREFERRED_PHONE_NUMBER_ID

        configured_waba_id = (os.getenv('WHATSAPP_BUSINESS_ACCOUNT_ID') or os.getenv('WHATSAPP_WABA_ID') or '').strip()
        waba_id = (
            os.getenv('WHATSAPP_ACTIVE_WABA_ID')
            or PREFERRED_WABA_ID
        ).strip()

        inactive_raw = (os.getenv('WHATSAPP_INACTIVE_PHONE_NUMBER_IDS') or '').strip()
        inactive_ids = {p.strip() for p in inactive_raw.split(',') if p.strip()}
        app_secret = (os.getenv('WHATSAPP_APP_SECRET') or '').strip() or None
        verify_token = (os.getenv('WHATSAPP_VERIFY_TOKEN') or 'postpilot_wa_verify_2026').strip()

        return {
            'access_token': token,
            'token_source': token_source,
            'phone_number_id': phone_id,
            'env_phone_number_id': configured_phone_id or None,
            'env_waba_id': configured_waba_id or None,
            'preferred_phone_number_id': PREFERRED_PHONE_NUMBER_ID,
            'preferred_waba_id': PREFERRED_WABA_ID,
            'waba_id': waba_id,
            'inactive_phone_number_ids': inactive_ids,
            'app_secret': app_secret,
            'verify_token': verify_token,
        }

    def validate_sender(
        self,
        requested_phone_number_id: Optional[str] = None,
        allow_preserved_sandbox: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Enforces strict sender-number isolation without mutating .env or falling back silently.
        +91 98257 28291 (1298748379987770) is the ONLY preferred sender offered by PostPilot.
        Secondary account +91 90990 28291 (1171737406016871) is preserved untouched and NEVER offered for broadcasting.
        """
        creds = self.get_credentials()
        configured = creds.get('phone_number_id')
        inactive_ids = creds.get('inactive_phone_number_ids') or set()

        target = str(requested_phone_number_id).strip() if requested_phone_number_id else configured
        if not target:
            return False, None, "No WhatsApp sender phone_number_id is configured."
        if target in inactive_ids:
            return False, None, f"Sender phone_number_id '{target}' is explicitly marked inactive and cannot dispatch."
        if target == LEGACY_DISCONNECTED_PHONE_NUMBER_ID:
            return False, None, "Secondary account +91 90990 28291 (1171737406016871) is preserved in read-only standby and is not offered for broadcasting."
        if requested_phone_number_id and configured and target != configured:
            return False, None, f"Sender mismatch: '{target}' does not match preferred sender '{configured}'."
        return True, target, None

    def validate_connection(self, **kwargs) -> Dict[str, Any]:
        """Validates credential configuration without making external requests."""
        creds = self.get_credentials()
        has_token = bool(creds['access_token'])
        has_phone_id = bool(creds['phone_number_id'])
        has_waba = bool(creds['waba_id'])

        return {
            'platform': self.platform_key,
            'configured': has_token and has_phone_id,
            'has_token': has_token,
            'token_source': creds['token_source'],
            'has_phone_number_id': has_phone_id,
            'phone_number_id': creds['phone_number_id'],
            'has_waba_id': has_waba,
            'waba_id': creds['waba_id'],
            'webhook_secret_configured': bool(creds['app_secret']),
            'publishing_enabled': config.is_platform_publishing_enabled('whatsapp'),
        }

    def check_token_health(self) -> Dict[str, Any]:
        """Safely verifies Meta token validity, expiry, and WhatsApp scopes via /debug_token without revealing the token."""
        creds = self.get_credentials()
        token = creds.get('access_token')
        if not token:
            return {'valid': False, 'expired': False, 'error': 'Missing access token.', 'scopes': [], 'missing_scopes': ['whatsapp_business_messaging', 'whatsapp_business_management']}

        try:
            resp = requests.get(
                f"{WHATSAPP_API_BASE}/debug_token",
                params={'input_token': token, 'access_token': token},
                timeout=10,
            )
            payload = resp.json()
            data = payload.get('data', {}) if isinstance(payload, dict) else {}
            if 'error' in payload or not data:
                err_msg = (payload.get('error') or {}).get('message', 'Token inspection failed') if isinstance(payload, dict) else 'Invalid response'
                return {'valid': False, 'expired': False, 'error': facebook_api.sanitize_log_message(err_msg), 'scopes': []}

            is_valid = bool(data.get('is_valid'))
            expires_at = int(data.get('expires_at') or 0)
            now_ts = int(time.time())
            is_expired = (expires_at > 0 and expires_at <= now_ts) or (not is_valid and 'expired' in str((data.get('error') or {}).get('message', '')).lower())
            scopes = data.get('scopes') or []
            req_scopes = ['whatsapp_business_messaging', 'whatsapp_business_management']
            missing_scopes = [s for s in req_scopes if s not in scopes]

            return {
                'valid': is_valid and not is_expired,
                'expired': is_expired,
                'expires_at': expires_at,
                'expires_never': expires_at == 0,
                'token_type': data.get('type'),
                'app_id': data.get('app_id'),
                'scopes': scopes,
                'missing_scopes': missing_scopes,
                'granular_scopes': data.get('granular_scopes') or [],
            }
        except Exception as e:
            return {'valid': False, 'expired': False, 'error': facebook_api.sanitize_log_message(str(e)), 'scopes': []}

    @staticmethod
    def classify_whatsapp_error(res_json: Any, status_code: Optional[int] = None) -> Dict[str, Any]:
        """Classifies Meta Cloud API WhatsApp error responses into structured diagnostics."""
        err = res_json.get('error', {}) if isinstance(res_json, dict) else {}
        if not isinstance(err, dict):
            return {'category': 'UNKNOWN_ERROR', 'code': status_code, 'message': facebook_api.sanitize_log_message(str(res_json)), 'retryable': False}

        code = err.get('code')
        msg = facebook_api.sanitize_log_message(err.get('message') or str(res_json))
        if code in WHATSAPP_ERROR_CLASSIFICATIONS:
            cat, hint = WHATSAPP_ERROR_CLASSIFICATIONS[code]
            retryable = cat == 'RATE_LIMIT'
            return {'category': cat, 'code': code, 'message': msg, 'hint': hint, 'retryable': retryable}

        if status_code and int(status_code) >= 500:
            return {'category': 'SERVER_ERROR', 'code': code or status_code, 'message': msg, 'retryable': True}
        return {'category': 'API_ERROR', 'code': code or status_code, 'message': msg, 'retryable': False}

    def validate_phone_number(self, phone_number: str) -> Tuple[bool, str]:
        """
        Validates and normalizes phone number to strict E.164 international format.
        Example: '+91 90990 28291' -> '+919099028291'
        """
        if not phone_number or not str(phone_number).strip():
            return False, "Phone number cannot be empty."

        clean = re.sub(r'[\s\-\(\)\.]', '', str(phone_number).strip())
        if not clean.startswith('+'):
            clean = '+' + clean

        if not re.match(r'^\+[1-9]\d{6,14}$', clean):
            return False, f"Invalid E.164 phone format: '{phone_number}'. Must include country code (e.g. +91...)"

        return True, clean

    def validate_template_variables(
        self,
        body_text: str,
        variables: Optional[List[Any]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validates {{1}}..{{N}} template placeholders against supplied variables or Meta components."""
        placeholders = sorted({int(m) for m in re.findall(r'\{\{(\d+)\}\}', str(body_text or ''))})
        if not placeholders:
            return True, None

        expected_seq = list(range(1, max(placeholders) + 1))
        if placeholders != expected_seq:
            return False, f"Template placeholders must be sequential starting at {{{{1}}}}; found {placeholders}."

        supplied: List[str] = []
        if isinstance(variables, list) and len(variables) > 0:
            supplied = [str(v).strip() for v in variables]
        elif isinstance(components, list):
            for comp in components:
                if isinstance(comp, dict) and str(comp.get('type', '')).lower() == 'body':
                    params = comp.get('parameters') or []
                    supplied = [str(p.get('text', '')).strip() for p in params if isinstance(p, dict)]
                    break

        if len(supplied) < len(expected_seq):
            return False, f"Template requires {len(expected_seq)} variable(s) ({expected_seq}), got {len(supplied)}."
        for idx, val in enumerate(supplied[:len(expected_seq)], 1):
            if not val:
                return False, f"Template variable {{{{{idx}}}}} cannot be empty."
            if '\n' in val or '\t' in val or '    ' in val:
                return False, f"Template variable {{{{{idx}}}}} cannot contain newlines, tabs, or 4+ consecutive spaces."

        return True, None

    def validate_content(self, content: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates WhatsApp message/template content and optional template variables."""
        template_name = content.get('template_name')
        message_text = content.get('message') or content.get('text') or ''

        if not template_name and not str(message_text).strip():
            return False, "WhatsApp broadcast requires an approved template name or message body."

        if len(str(message_text)) > 4096:
            return False, f"WhatsApp message exceeds 4,096 character limit ({len(str(message_text))} chars)."

        if template_name and not re.match(r'^[a-z0-9_]{1,512}$', str(template_name).strip()):
            return False, f"Invalid Meta template name format: '{template_name}'."

        if content.get('recipient_phone') or content.get('phone'):
            valid_p, p_err = self.validate_phone_number(content.get('recipient_phone') or content.get('phone'))
            if not valid_p:
                return False, p_err

        body_for_vars = str(message_text or '')
        if not body_for_vars and template_name:
            for t in self.get_local_template_previews():
                if t['name'] == template_name:
                    body_for_vars = t.get('body_text', '')
                    break

        if body_for_vars and (content.get('variables') is not None or content.get('components') is not None or '{{' in body_for_vars):
            ok_v, err_v = self.validate_template_variables(
                body_for_vars,
                variables=content.get('variables'),
                components=content.get('components'),
            )
            if not ok_v:
                return False, err_v

        return True, None

    def upload_media(self, file_path: str, media_type: str = 'image', **kwargs) -> Dict[str, Any]:
        """Validates media header attachments for WhatsApp templates."""
        if not os.path.isfile(file_path):
            return {'success': False, 'error': f"Media file not found: {file_path}"}
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.mp4', '.pdf'):
            return {'success': False, 'error': f"Unsupported WhatsApp media format: '{ext}'."}
        return {'success': True, 'path': file_path, 'filename': os.path.basename(file_path)}

    def get_local_template_previews(self) -> List[Dict[str, Any]]:
        """
        Returns local sandbox template previews with explicit LOCAL_PREVIEW status.
        NEVER marked APPROVED; includes Meta submission payloads prepared for authorized review.
        """
        return [
            {
                'name': 'client_welcome',
                'label': 'Client Welcome & Onboarding',
                'category': 'UTILITY',
                'language': 'en',
                'status': 'LOCAL_PREVIEW',
                'meta_approved': False,
                'is_local_preview': True,
                'header_type': 'TEXT',
                'body_text': 'Welcome to {{1}}! We are thrilled to partner with you on your strategic growth journey. Our advisory team will reach out shortly with your tailored roadmap.',
                'example_vars': ['Gaatha Ventures'],
                'submission_ready': True,
                'submission_payload': {
                    'name': 'client_welcome',
                    'language': 'en',
                    'category': 'UTILITY',
                    'components': [
                        {
                            'type': 'BODY',
                            'text': 'Welcome to {{1}}! We are thrilled to partner with you on your strategic growth journey. Our advisory team will reach out shortly with your tailored roadmap.',
                            'example': {'body_text': [['Gaatha Ventures']]},
                        }
                    ],
                },
            },
            {
                'name': 'consultation_reminder',
                'label': 'Consultation Session Reminder',
                'category': 'UTILITY',
                'language': 'en',
                'status': 'LOCAL_PREVIEW',
                'meta_approved': False,
                'is_local_preview': True,
                'header_type': 'TEXT',
                'body_text': 'Reminder: Your upcoming strategic consultation with {{1}} is scheduled for {{2}}. Reference ID: {{3}}.',
                'example_vars': ['Gaatha Ventures', 'tomorrow at 11:00 AM IST', 'REF-2026-11'],
                'submission_ready': True,
                'submission_payload': {
                    'name': 'consultation_reminder',
                    'language': 'en',
                    'category': 'UTILITY',
                    'components': [
                        {
                            'type': 'BODY',
                            'text': 'Reminder: Your upcoming strategic consultation with {{1}} is scheduled for {{2}}. Reference ID: {{3}}.',
                            'example': {'body_text': [['Gaatha Ventures', 'tomorrow at 11:00 AM IST', 'REF-2026-11']]},
                        }
                    ],
                },
            },
            {
                'name': 'campaign_announcement',
                'label': 'Marketing Campaign Announcement',
                'category': 'MARKETING',
                'language': 'en',
                'status': 'LOCAL_PREVIEW',
                'meta_approved': False,
                'is_local_preview': True,
                'header_type': 'TEXT',
                'body_text': 'Hello {{1}}, explore {{2}} and our latest digital solutions built by Aidni Global LLP & Gaatha Ventures. Visit {{3}} to learn more.',
                'example_vars': ['Valued Partner', 'GAATHA Ecosystem Live Beta', 'https://gaatha.tech/'],
                'submission_ready': True,
                'submission_payload': {
                    'name': 'campaign_announcement',
                    'language': 'en',
                    'category': 'MARKETING',
                    'components': [
                        {
                            'type': 'BODY',
                            'text': 'Hello {{1}}, explore {{2}} and our latest digital solutions built by Aidni Global LLP & Gaatha Ventures. Visit {{3}} to learn more.',
                            'example': {'body_text': [['Valued Partner', 'GAATHA Ecosystem Live Beta', 'https://gaatha.tech/']]},
                        }
                    ],
                },
            },
            {
                'name': 'custom_direct',
                'label': 'Custom Business Message',
                'category': 'CONVERSATIONAL',
                'language': 'en',
                'status': 'LOCAL_PREVIEW',
                'meta_approved': False,
                'is_local_preview': True,
                'header_type': 'NONE',
                'body_text': 'Hello from Gaatha Ventures. Thank you for your inquiry. We are reviewing your requirements and will provide an update shortly.',
                'example_vars': [],
                'submission_ready': False,
                'submission_note': 'Free-form session reply allowed only within an active 24-hour customer service window; not submitted as a static template.',
            },
        ]

    def fetch_live_templates(self, waba_id: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
        """Fetches live message templates directly from Meta Graph API without inventing approvals."""
        creds = self.get_credentials()
        token = creds.get('access_token')
        target_waba = (waba_id or creds.get('waba_id') or '').strip()
        if not token or not target_waba:
            return {'success': False, 'waba_id': target_waba, 'templates': [], 'approved_count': 0, 'error': 'Missing token or WABA ID.'}

        try:
            resp = requests.get(
                f"{WHATSAPP_API_BASE}/{target_waba}/message_templates",
                params={'fields': 'id,name,status,category,language,rejected_reason,components', 'limit': 100},
                headers={'Authorization': f'Bearer {token}'},
                timeout=timeout,
            )
            data = resp.json()
            if resp.status_code != 200 or 'error' in data:
                diag = self.classify_whatsapp_error(data, resp.status_code)
                return {'success': False, 'waba_id': target_waba, 'templates': [], 'approved_count': 0, 'error': diag['message'], 'classification': diag}

            rows = data.get('data', [])
            for item in rows:
                item['meta_approved'] = str(item.get('status', '')).upper() == 'APPROVED'
                item['is_local_preview'] = False
            approved = [t for t in rows if t.get('meta_approved')]
            return {
                'success': True,
                'waba_id': target_waba,
                'templates': rows,
                'approved_count': len(approved),
            }
        except Exception as e:
            return {'success': False, 'waba_id': target_waba, 'templates': [], 'approved_count': 0, 'error': facebook_api.sanitize_log_message(str(e))}

    def get_templates(self, include_live: bool = False, waba_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns local template previews (marked LOCAL_PREVIEW, meta_approved=False) by default,
        or actual Meta-fetched templates when include_live=True. Never labels previews as APPROVED.
        """
        if include_live:
            live_res = self.fetch_live_templates(waba_id=waba_id)
            return live_res.get('templates', [])
        return self.get_local_template_previews()

    def send_template(
        self,
        recipient_phone: str,
        template_name: str,
        language_code: str = 'en',
        components: Optional[List[Dict[str, Any]]] = None,
        variables: Optional[List[Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Dispatches an approved WhatsApp Business template message.
        When WHATSAPP_PUBLISHING_ENABLED=0, validates inputs and simulates without external API calls.
        """
        valid_phone, normalized_phone = self.validate_phone_number(recipient_phone)
        if not valid_phone:
            return {'success': False, 'error': normalized_phone}

        is_sandbox = not config.is_platform_publishing_enabled('whatsapp')
        sender_ok, phone_number_id, sender_err = self.validate_sender(kwargs.get('phone_number_id'), allow_preserved_sandbox=is_sandbox)
        if not sender_ok:
            return {'success': False, 'error': sender_err}

        if not template_name or not re.match(r'^[a-z0-9_]{1,512}$', str(template_name).strip()):
            return {'success': False, 'error': f"Invalid Meta template name format: '{template_name}'."}

        # Validate template variables if variable list/components supplied or template preview defines placeholders
        if variables is not None or components is not None:
            tpl_match = next((t for t in self.get_local_template_previews() if t['name'] == template_name), None)
            if tpl_match:
                ok_v, err_v = self.validate_template_variables(tpl_match.get('body_text', ''), variables=variables, components=components)
                if not ok_v:
                    return {'success': False, 'error': err_v}

        # Build components cleanly when variables are provided as a list
        resolved_components = list(components or [])
        if variables and not resolved_components:
            resolved_components = [{
                'type': 'body',
                'parameters': [{'type': 'text', 'text': str(v).strip()} for v in variables]
            }]

        creds = self.get_credentials()

        # Safety Guardrail: Intercept when WhatsApp publishing is disabled
        if not config.is_platform_publishing_enabled('whatsapp'):
            sim_msg_id = f"wamid.sim_{int(time.time() * 1000)}_{normalized_phone[-4:]}"
            logger.info(
                f"🛡️ [SAFETY] WhatsApp template dispatch simulated (WHATSAPP_PUBLISHING_ENABLED=0): "
                f"Sender={phone_number_id}, Recipient={normalized_phone}, Template={template_name}, Lang={language_code}"
            )
            return {
                'success': True,
                'platform': self.platform_key,
                'external_message_id': sim_msg_id,
                'external_post_id': sim_msg_id,
                'sender_phone_number_id': phone_number_id,
                'recipient_phone': normalized_phone,
                'template_name': template_name,
                'simulated': True,
                'message': 'Simulated broadcast: WHATSAPP_PUBLISHING_ENABLED is 0'
            }

        if not creds['access_token'] or not phone_number_id:
            return {'success': False, 'error': 'Missing WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID.'}

        url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone.replace('+', ''),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": resolved_components
            }
        }

        res = facebook_api._request_with_retry("POST", url, json=payload, headers=headers)
        if not res or 'messages' not in res:
            diag = self.classify_whatsapp_error(res)
            logger.error(f"WhatsApp Cloud API dispatch error ({diag['category']}) to {normalized_phone}: {diag['message']}")
            return {'success': False, 'error': diag['message'], 'error_category': diag['category'], 'error_code': diag.get('code')}

        msg_id = res['messages'][0]['id']
        return {
            'success': True,
            'platform': self.platform_key,
            'external_message_id': msg_id,
            'sender_phone_number_id': phone_number_id,
            'recipient_phone': normalized_phone,
            'simulated': False,
            'response': res
        }

    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Publishes a WhatsApp template message while enforcing brand and sender isolation."""
        brand_id = payload.get('brand_id')
        org_id = int(payload.get('organization_id', 1))
        if brand_id is not None:
            try:
                import database
                acct = database.get_social_account_for_brand(org_id, int(brand_id), 'whatsapp')
            except Exception:
                acct = None
            if not acct:
                logger.warning(f"No WhatsApp account mapped for brand #{brand_id}. Cross-brand inheritance blocked.")
                return {'success': False, 'platform': self.platform_key, 'error': f"No WhatsApp account mapped for brand #{brand_id}. Cross-brand inheritance blocked."}

        recipient = payload.get('recipient_phone') or payload.get('phone')
        template = payload.get('template_name') or 'client_welcome'
        lang = payload.get('language_code') or 'en'
        components = payload.get('components')
        variables = payload.get('variables')

        return self.send_template(
            recipient_phone=recipient,
            template_name=template,
            language_code=lang,
            components=components,
            variables=variables,
            phone_number_id=payload.get('phone_number_id'),
        )

    def verify_webhook_signature(self, payload_bytes: bytes, signature_header: str, app_secret: Optional[str] = None) -> bool:
        """
        Verifies SHA-256 HMAC signature sent in 'X-Hub-Signature-256'.
        Enforces Meta webhook cryptographic authenticity (fail-closed when secret is missing).
        """
        if not app_secret:
            creds = self.get_credentials()
            app_secret = creds.get('app_secret')
        if not app_secret:
            logger.warning("WHATSAPP_APP_SECRET is not configured; cannot verify webhook signature.")
            return False

        if not signature_header or not signature_header.startswith('sha256='):
            return False

        expected_sig = signature_header.split('sha256=')[1].strip()
        computed_sig = hmac.new(
            app_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed_sig, expected_sig)

    def get_status(self) -> Dict[str, Any]:
        """Returns structured health and honest template/webhook readiness status for WhatsApp."""
        creds = self.get_credentials()
        conn = self.validate_connection()
        local_previews = self.get_local_template_previews()
        return {
            'platform': self.platform_key,
            'display_name': self.display_name,
            'configured': conn['configured'],
            'phone_number_id': creds['phone_number_id'],
            'waba_id': creds['waba_id'],
            'publishing_enabled': config.is_platform_publishing_enabled('whatsapp'),
            'webhook_secret_configured': bool(creds['app_secret']),
            'templates_count': 0,
            'meta_approved_templates_count': 0,
            'local_preview_templates_count': len(local_previews),
        }
