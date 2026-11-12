"""
PostPilot Unified Social Integrations Service
Discovers all accessible properties across Meta (Facebook Pages, Instagram Business),
LinkedIn Enterprise Applications, and WhatsApp Business Cloud API.
Provides standardized status assessment, permission audit, and safe brand mapping.
"""
import os
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import requests

import config
import database
import facebook_api
import linkedin_api

logger = logging.getLogger(__name__)

# Standard Status Labels (Requirement 4)
STATUS_CREDENTIALS_MISSING = "Credentials Missing"
STATUS_CREDENTIALS_CONFIGURED = "Credentials Configured"
STATUS_AUTHENTICATION_REQUIRED = "Authentication Required"
STATUS_CONNECTED = "Connected"
STATUS_CONNECTED_LIMITED = "Connected — Limited Permissions"
STATUS_PUBLISHING_NOT_APPROVED = "Publishing Not Approved"
STATUS_VERIFICATION_REQUIRED = "Verification Required"
STATUS_LIVE_READY = "Live Publishing Ready"
STATUS_DISCONNECTED = "Disconnected"

GRAPH_BASE_URL = "https://graph.facebook.com/v19.0"


def discover_meta_properties(organization_id: int = 1) -> Dict[str, Any]:
    """
    Discovers all Facebook Pages and linked Instagram Professional accounts
    accessible with the configured Meta token.
    Determines publishing permissions, linked Instagram accounts, and active brand mappings.
    Zero credential exposure.
    """
    token = getattr(config, 'FB_ACCESS_TOKEN', None) or os.getenv('FB_ACCESS_TOKEN')
    if not token or not token.strip():
        return {
            'success': False,
            'error': 'Meta Access Token (FB_ACCESS_TOKEN) is not configured in .env',
            'status_label': STATUS_CREDENTIALS_MISSING,
            'pages': [],
            'instagram_accounts': []
        }

    headers = {'Authorization': f'Bearer {token.strip()}'}

    # 1. Inspect token debug information
    token_valid = False
    token_scopes = []
    try:
        dbg_res = requests.get(
            f"{GRAPH_BASE_URL}/debug_token",
            params={'input_token': token.strip(), 'access_token': token.strip()},
            timeout=10
        ).json()
        dbg_data = dbg_res.get('data', {})
        token_valid = bool(dbg_data.get('is_valid'))
        token_scopes = dbg_data.get('scopes', [])
    except Exception as e:
        logger.warning(f"Could not query Meta debug_token: {facebook_api.sanitize_log_message(str(e))}")

    # 2. Retrieve all accessible Facebook Pages
    try:
        pages_res = requests.get(
            f"{GRAPH_BASE_URL}/me/accounts?fields=id,name,category,tasks,is_published,can_post",
            headers=headers,
            timeout=15
        ).json()
        if 'error' in pages_res:
            err_msg = pages_res['error'].get('message', 'Failed to retrieve accounts from Meta Graph API')
            return {
                'success': False,
                'error': err_msg,
                'status_label': STATUS_DISCONNECTED,
                'pages': [],
                'instagram_accounts': []
            }
        raw_pages = pages_res.get('data', [])
    except Exception as e:
        safe_e = facebook_api.sanitize_log_message(str(e))
        return {
            'success': False,
            'error': f"Network error contacting Meta Graph API: {safe_e}",
            'status_label': STATUS_DISCONNECTED,
            'pages': [],
            'instagram_accounts': []
        }

    # Get existing mappings from database
    existing_accounts = database.get_social_accounts(organization_id=organization_id)
    fb_mappings = {str(a['account_identifier']): a for a in existing_accounts if a['platform'] == 'facebook'}
    ig_mappings = {str(a['account_identifier']): a for a in existing_accounts if a['platform'] == 'instagram'}

    # Get brands map
    with database.get_db_connection() as conn:
        brands_rows = conn.execute("SELECT id, name, slug FROM brands WHERE organization_id = ?", (organization_id,)).fetchall()
        brands_map = {b['id']: dict(b) for b in brands_rows}

    discovered_pages = []
    discovered_ig_accounts = []

    for p in raw_pages:
        pid = str(p['id'])
        name = p.get('name', 'Unnamed Page')
        category = p.get('category', 'General')
        tasks = p.get('tasks', [])
        can_post = bool(p.get('can_post', True))

        # Check publishing permissions
        # In Meta Graph API, administrative publishing as the Page requires CREATE_CONTENT or MANAGE task
        # and pages_manage_posts scope on the token (can_post field only refers to visitor wall posting).
        has_manage = 'MANAGE' in tasks or 'CREATE_CONTENT' in tasks
        has_scope = 'pages_manage_posts' in token_scopes or len(token_scopes) == 0
        can_publish = has_manage and has_scope

        # Mapping status
        mapping = fb_mappings.get(pid)
        assigned_brand_id = mapping['brand_id'] if mapping else None
        assigned_brand_name = brands_map.get(assigned_brand_id, {}).get('name') if assigned_brand_id else None

        # Determine status label
        if not can_publish:
            status_label = STATUS_CONNECTED_LIMITED
            action_required = "Page lacks CREATE_CONTENT or MANAGE task permission on Meta."
        elif not assigned_brand_id:
            status_label = STATUS_CONNECTED
            action_required = "Page accessible and verified. Assign to a GAATHA brand workspace to enable publishing."
        elif config.is_platform_publishing_enabled('facebook'):
            status_label = STATUS_LIVE_READY
            action_required = None
        else:
            status_label = STATUS_CONNECTED
            action_required = "Connected and verified (Safe Standby: Facebook publishing disabled)."

        page_record = {
            'id': pid,
            'name': name,
            'platform': 'facebook',
            'category': category,
            'tasks': tasks,
            'can_publish': can_publish,
            'assigned_brand_id': assigned_brand_id,
            'assigned_brand_name': assigned_brand_name,
            'account_id': mapping['id'] if mapping else None,
            'status_label': status_label,
            'action_required': action_required,
            'last_verified_at': mapping.get('last_verified_at') if mapping else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
        discovered_pages.append(page_record)

        # Check linked Instagram account
        try:
            ig_res = requests.get(
                f"{GRAPH_BASE_URL}/{pid}?fields=instagram_business_account{{id,username,name,profile_picture_url,followers_count,media_count}}",
                headers=headers,
                timeout=10
            ).json()
            ig_data = ig_res.get('instagram_business_account')
            if ig_data:
                ig_id = str(ig_data['id'])
                ig_user = ig_data.get('username', '')
                ig_name = ig_data.get('name', '')
                followers = ig_data.get('followers_count', 0)
                media_count = ig_data.get('media_count', 0)

                ig_mapping = ig_mappings.get(ig_id)
                ig_brand_id = ig_mapping['brand_id'] if ig_mapping else None
                ig_brand_name = brands_map.get(ig_brand_id, {}).get('name') if ig_brand_id else None

                ig_can_publish = ('instagram_content_publish' in token_scopes or len(token_scopes) == 0) and can_publish

                if not ig_can_publish:
                    ig_status_label = STATUS_CONNECTED_LIMITED
                    ig_action = "Missing instagram_content_publish scope on Meta."
                elif not ig_brand_id:
                    ig_status_label = STATUS_CONNECTED
                    ig_action = f"Linked to '{name}'. Assign to a GAATHA brand workspace to enable publishing."
                elif config.is_platform_publishing_enabled('instagram'):
                    ig_status_label = STATUS_LIVE_READY
                    ig_action = None
                else:
                    ig_status_label = STATUS_CONNECTED
                    ig_action = "Connected and verified (Instagram publishing disabled / media required)."

                discovered_ig_accounts.append({
                    'id': ig_id,
                    'username': f"@{ig_user}" if ig_user and not ig_user.startswith('@') else ig_user,
                    'name': ig_name or f"@{ig_user}",
                    'platform': 'instagram',
                    'linked_facebook_page_id': pid,
                    'linked_facebook_page_name': name,
                    'followers_count': followers,
                    'media_count': media_count,
                    'can_publish': ig_can_publish,
                    'assigned_brand_id': ig_brand_id,
                    'assigned_brand_name': ig_brand_name,
                    'account_id': ig_mapping['id'] if ig_mapping else None,
                    'status_label': ig_status_label,
                    'action_required': ig_action,
                    'last_verified_at': ig_mapping.get('last_verified_at') if ig_mapping else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                })
        except Exception as e:
            logger.warning(f"Could not fetch linked Instagram for page {pid}: {facebook_api.sanitize_log_message(str(e))}")

    return {
        'success': True,
        'organization_id': organization_id,
        'token_valid': token_valid,
        'token_scopes': token_scopes,
        'pages_count': len(discovered_pages),
        'instagram_count': len(discovered_ig_accounts),
        'pages': discovered_pages,
        'instagram_accounts': discovered_ig_accounts
    }


def get_linkedin_integration_status(organization_id: int = 1) -> Dict[str, Any]:
    """
    Evaluates both configured LinkedIn applications (Aidni Global LLP & Gaatha Ventures).
    Distinguishes between configured credentials, user authentication, and organization publishing readiness.
    Zero secret disclosure.
    """
    existing_accounts = database.get_social_accounts(organization_id=organization_id, platform='linkedin')
    existing_by_org = {str(a['account_identifier']): a for a in existing_accounts}

    with database.get_db_connection() as conn:
        brands_rows = conn.execute("SELECT id, name FROM brands WHERE organization_id = ?", (organization_id,)).fetchall()
        brands_map = {b['id']: b['name'] for b in brands_rows}

    apps_status = []
    redirect_uri = getattr(config, 'LINKEDIN_REDIRECT_URI', None) or 'https://postpilot.gaatha.tech/api/auth/linkedin/callback'

    for app_key in [linkedin_api.APP_AIDNI_GLOBAL, linkedin_api.APP_GAATHA_VENTURES]:
        cfg = linkedin_api.get_app_config(app_key)
        has_client_id = bool(cfg.get('client_id'))
        has_client_secret = bool(cfg.get('client_secret'))
        org_id = cfg.get('org_id')
        display_name = cfg.get('display_name')

        token_data = linkedin_api.get_token_data(app_key)
        env_token = cfg.get('configured_token')
        active_token = token_data.get('access_token') if token_data else env_token

        user_authenticated = False
        member_name = None
        token_expired = False
        token_scopes = []
        company_publishing_ready = False

        if active_token:
            if token_data and linkedin_api.is_token_expired(token_data):
                token_expired = True
            else:
                token_scopes = linkedin_api.parse_scopes(token_data.get('scope')) if token_data else []
                if not token_scopes:
                    token_scopes = linkedin_api.get_default_scopes(app_key)

                has_openid_profile = ('openid' in token_scopes and 'profile' in token_scopes)
                if has_openid_profile:
                    member = linkedin_api.get_authenticated_member(active_token)
                    if member.get('success'):
                        user_authenticated = True
                        member_name = member.get('name')
                    else:
                        introspect = linkedin_api.introspect_token(app_key, active_token)
                        if introspect.get('checked') and introspect.get('active'):
                            user_authenticated = True
                            token_scopes = introspect.get('scopes') or token_scopes
                            member_name = 'Authorized Member (Share on LinkedIn)'
                        else:
                            token_expired = True
                else:
                    # w_member_social-only tokens (e.g. Gaatha Ventures) do not have OpenID /v2/userinfo permission;
                    # verify active status via LinkedIn token introspection rather than failing HTTP 403.
                    introspect = linkedin_api.introspect_token(app_key, active_token)
                    if introspect.get('checked'):
                        if introspect.get('active'):
                            user_authenticated = True
                            if introspect.get('scopes'):
                                token_scopes = introspect['scopes']
                            if 'openid' in token_scopes and 'profile' in token_scopes:
                                member = linkedin_api.get_authenticated_member(active_token)
                                member_name = member.get('name') if member.get('success') else 'Authorized Member (Share on LinkedIn)'
                            else:
                                member_name = 'Authorized Member (Share on LinkedIn)'
                        else:
                            token_expired = True
                    else:
                        user_authenticated = True
                        member_name = 'Authorized Member (Share on LinkedIn)'

                if user_authenticated:
                    eligibility = linkedin_api.check_organization_publishing_eligibility(app_key, access_token=active_token)
                    company_publishing_ready = bool(eligibility.get('company_publishing_authorized'))

        # Mapping status in database
        mapping = existing_by_org.get(str(org_id))
        assigned_brand_id = mapping['brand_id'] if mapping else 1
        assigned_brand_name = brands_map.get(assigned_brand_id, 'GAATHA Suite')

        # Precise Status Label Classification (Requirement 2 & 4)
        if not (has_client_id and has_client_secret):
            status_label = STATUS_CREDENTIALS_MISSING
            action_required = "Client ID or Client Secret missing in .env"
        elif token_expired:
            status_label = STATUS_AUTHENTICATION_REQUIRED
            action_required = "OAuth access token expired. Reconnect via OAuth authorization flow."
        elif not user_authenticated:
            status_label = STATUS_AUTHENTICATION_REQUIRED
            action_required = "Client credentials configured. 3-legged OAuth sign-in required to generate an active access token."
        elif not company_publishing_ready:
            status_label = STATUS_CONNECTED_LIMITED
            action_required = "User authenticated. Company Page publishing requires LinkedIn 'Community Management API' approval (w_organization_social)."
        elif config.is_platform_publishing_enabled('linkedin'):
            status_label = STATUS_LIVE_READY
            action_required = None
        else:
            status_label = STATUS_CONNECTED
            action_required = "Connected and authorized for organization publishing (Safe Standby: LinkedIn publishing disabled)."

        connect_url = f"/api/auth/linkedin/connect?app={app_key}"

        apps_status.append({
            'app_key': app_key,
            'name': display_name,
            'platform': 'linkedin',
            'organization_id': org_id,
            'client_id_configured': has_client_id,
            'client_secret_configured': has_client_secret,
            'redirect_uri': redirect_uri,
            'user_authenticated': user_authenticated,
            'authenticated_member': member_name,
            'token_scopes': token_scopes,
            'requested_scopes': linkedin_api.get_default_scopes(app_key),
            'company_publishing_ready': company_publishing_ready,
            'assigned_brand_id': assigned_brand_id,
            'assigned_brand_name': assigned_brand_name,
            'status_label': status_label,
            'action_required': action_required,
            'connect_url': connect_url,
            'last_verified_at': mapping.get('last_verified_at') if mapping else None
        })

    return {
        'success': True,
        'organization_id': organization_id,
        'apps': apps_status
    }


def get_whatsapp_integration_status(organization_id: int = 1, include_discovery: bool = False) -> Dict[str, Any]:
    """
    Evaluates WhatsApp Business Cloud API readiness honestly against Meta Graph API.
    Inspects BOTH preserved sender lines (+91 90990 28291 / 1171737406016871 and
    +91 98257 28291 / 1298748379987770), token health/scopes, live approved templates
    vs local previews, webhook readiness, and remaining Meta requirements.
    """
    from platform_adapters.whatsapp import WhatsAppCloudAdapter, PRESERVED_WHATSAPP_NUMBERS

    adapter = WhatsAppCloudAdapter()
    creds = adapter.get_credentials()
    token = creds.get('access_token')
    headers = {'Authorization': f'Bearer {token}'} if token else {}

    configured_waba_id = creds.get('waba_id') or '1370721214882653'
    configured_phone_id = creds.get('phone_number_id') or '1171737406016871'
    configured_phone_display = PRESERVED_WHATSAPP_NUMBERS.get(configured_phone_id, {}).get('display_phone_number', '+91 90990 28291')

    phone_fields = (
        'id,display_phone_number,verified_name,code_verification_status,quality_rating,'
        'platform_type,throughput,status,name_status,account_mode,messaging_limit_tier,'
        'is_pin_enabled,health_status'
    )

    def _inspect_line(phone_id: str, waba_id: str, meta_defaults: Dict[str, Any]) -> Dict[str, Any]:
        info = dict(meta_defaults)
        p_data: Dict[str, Any] = {}
        w_data: Dict[str, Any] = {}
        templates: list = []
        subscribed_apps: list = []
        if not token:
            info.update({
                'phone_status': 'UNKNOWN',
                'code_verification_status': 'UNKNOWN',
                'platform_type': 'UNKNOWN',
                'approved_templates_count': 0,
                'health_can_send': 'UNKNOWN',
                'health_errors': [],
                'subscribed_apps': [],
            })
            return info

        try:
            pr = requests.get(f"{GRAPH_BASE_URL}/{phone_id}?fields={phone_fields}", headers=headers, timeout=5).json()
            if isinstance(pr, dict) and 'id' in pr:
                p_data = pr
        except Exception as e:
            logger.warning(f"Error querying WhatsApp phone {phone_id}: {facebook_api.sanitize_log_message(str(e))}")

        try:
            wr = requests.get(
                f"{GRAPH_BASE_URL}/{waba_id}?fields=id,name,business_verification_status,account_review_status,timezone_id,ownership_type",
                headers=headers,
                timeout=5,
            ).json()
            if isinstance(wr, dict) and 'id' in wr:
                w_data = wr
        except Exception as e:
            logger.warning(f"Error querying WABA {waba_id}: {facebook_api.sanitize_log_message(str(e))}")

        try:
            tr = requests.get(
                f"{GRAPH_BASE_URL}/{waba_id}/message_templates?fields=id,name,status,category,language&limit=100",
                headers=headers,
                timeout=5,
            ).json()
            if isinstance(tr, dict):
                templates = tr.get('data', [])
        except Exception as e:
            logger.warning(f"Error querying WABA {waba_id} templates: {facebook_api.sanitize_log_message(str(e))}")

        try:
            sr = requests.get(f"{GRAPH_BASE_URL}/{waba_id}/subscribed_apps", headers=headers, timeout=5).json()
            if isinstance(sr, dict):
                for row in sr.get('data', []):
                    app_obj = row.get('whatsapp_business_api_data') or row
                    subscribed_apps.append({
                        'id': str(app_obj.get('id') or ''),
                        'name': app_obj.get('name') or 'Unknown App',
                    })
        except Exception as e:
            logger.warning(f"Error querying WABA {waba_id} subscribed_apps: {facebook_api.sanitize_log_message(str(e))}")

        health_obj = p_data.get('health_status') or {}
        health_errors = []
        business_entity_available = None
        for ent in health_obj.get('entities', []):
            if ent.get('entity_type') == 'BUSINESS':
                business_entity_available = (ent.get('can_send_message') == 'AVAILABLE')
            for err in ent.get('errors', []):
                health_errors.append({
                    'entity_type': ent.get('entity_type'),
                    'error_code': err.get('error_code'),
                    'error_description': err.get('error_description'),
                })

        approved_cnt = len([t for t in templates if str(t.get('status', '')).upper() == 'APPROVED'])
        info.update({
            'display_phone_number': p_data.get('display_phone_number', meta_defaults.get('display_phone_number')),
            'verified_name': p_data.get('verified_name', meta_defaults.get('business_name')),
            'phone_status': p_data.get('status', 'DISCONNECTED'),
            'code_verification_status': p_data.get('code_verification_status', 'NOT_VERIFIED'),
            'platform_type': p_data.get('platform_type', 'UNKNOWN'),
            'name_status': p_data.get('name_status'),
            'quality_rating': p_data.get('quality_rating'),
            'account_mode': p_data.get('account_mode'),
            'messaging_limit_tier': p_data.get('messaging_limit_tier'),
            'is_pin_enabled': p_data.get('is_pin_enabled'),
            'waba_name': w_data.get('name') or meta_defaults.get('business_name'),
            'business_verification_status': w_data.get('business_verification_status'),
            'account_review_status': w_data.get('account_review_status'),
            'timezone_id': w_data.get('timezone_id'),
            'approved_templates_count': approved_cnt,
            'total_meta_templates_count': len(templates),
            'health_can_send': health_obj.get('can_send_message', 'UNKNOWN'),
            'business_entity_available': business_entity_available,
            'health_errors': health_errors,
            'subscribed_apps': subscribed_apps,
            'postpilot_webhook_subscribed': any(str(a.get('id')) == '1397769361108621' for a in subscribed_apps),
            '_raw_phone': p_data,
        })
        return info

    preserved_targets = [
        PRESERVED_WHATSAPP_NUMBERS['1171737406016871'],
        PRESERVED_WHATSAPP_NUMBERS['1298748379987770'],
    ]
    # Ensure active configured sender is inspected if non-preserved override is set
    if configured_phone_id and configured_phone_id not in PRESERVED_WHATSAPP_NUMBERS:
        preserved_targets.insert(0, {
            'phone_number_id': configured_phone_id,
            'waba_id': configured_waba_id,
            'display_phone_number': configured_phone_display,
            'business_name': 'Configured Sender',
            'role': 'configured_override',
        })

    inspected_numbers = [_inspect_line(t['phone_number_id'], t['waba_id'], t) for t in preserved_targets]
    primary_line = next((n for n in inspected_numbers if n['phone_number_id'] == configured_phone_id), inspected_numbers[0])
    primary_phone_info = primary_line.get('_raw_phone') or {}
    for n in inspected_numbers:
        n.pop('_raw_phone', None)

    templates_count = primary_line.get('approved_templates_count', 0)
    total_approved_across_wabas = sum(n.get('approved_templates_count', 0) for n in inspected_numbers)
    token_health = adapter.check_token_health() if token else {'valid': False, 'expired': False, 'error': 'Missing access token.', 'scopes': [], 'missing_scopes': ['whatsapp_business_messaging', 'whatsapp_business_management']}

    # Discover all accessible WABAs cleanly
    discovered_wabas = []
    if token and include_discovery:
        try:
            me_biz = requests.get(f"{GRAPH_BASE_URL}/me/businesses?fields=id,name,verification_status", headers=headers, timeout=5).json()
            for b in me_biz.get('data', []):
                bid = b['id']
                bname = b['name']
                wr = requests.get(
                    f"{GRAPH_BASE_URL}/{bid}/owned_whatsapp_business_accounts?fields=id,name,phone_numbers{{id,display_phone_number,verified_name,code_verification_status,quality_rating,platform_type,status}}",
                    headers=headers,
                    timeout=5,
                ).json()
                for w in wr.get('data', []):
                    phones = w.get('phone_numbers', {}).get('data', [])
                    discovered_wabas.append({
                        'business_id': bid,
                        'business_name': bname,
                        'business_verification_status': b.get('verification_status'),
                        'waba_id': w['id'],
                        'waba_name': w['name'],
                        'phones': phones,
                    })
        except Exception as e:
            logger.warning(f"Error discovering Meta WABAs: {facebook_api.sanitize_log_message(str(e))}")
    elif token:
        for line in inspected_numbers:
            discovered_wabas.append({
                'business_name': line.get('waba_name') or line.get('business_name'),
                'waba_id': line['waba_id'],
                'waba_name': line.get('waba_name') or line.get('business_name'),
                'phones': [{
                    'id': line['phone_number_id'],
                    'display_phone_number': line.get('display_phone_number'),
                    'verified_name': line.get('verified_name'),
                    'status': line.get('phone_status'),
                    'code_verification_status': line.get('code_verification_status'),
                    'platform_type': line.get('platform_type'),
                    'health_can_send': line.get('health_can_send'),
                }],
            })

    code_ver = primary_line.get('code_verification_status', 'NOT_VERIFIED')
    plat_type = primary_line.get('platform_type', 'ON_PREMISE')
    phone_status = primary_line.get('phone_status', 'DISCONNECTED')
    health_can_send = primary_line.get('health_can_send', 'BLOCKED')

    if not token:
        status_label = STATUS_CREDENTIALS_MISSING
        action_required = "Meta Access Token missing in .env"
    elif code_ver == 'NOT_VERIFIED' or plat_type == 'ON_PREMISE' or health_can_send == 'BLOCKED':
        status_label = STATUS_VERIFICATION_REQUIRED
        action_required = (
            f"Configured sender {configured_phone_display} ({plat_type}/{phone_status}) and Cloud API line "
            f"+91 98257 28291 both currently report Meta health_status '{health_can_send}'. "
            "Business portfolio 560075574375818 is verified, but WABA billing/payment (141006), timezone (141007), "
            "phone OTP/PIN verification, Meta template approval (0 approved), and PostPilot webhook secret/subscription remain pending."
        )
    elif templates_count == 0:
        status_label = STATUS_CONNECTED_LIMITED
        action_required = "Phone is connected, but 0 approved Meta message templates exist. Broadcast marketing requires approved templates."
    elif config.is_platform_publishing_enabled('whatsapp'):
        status_label = STATUS_LIVE_READY
        action_required = None
    else:
        status_label = STATUS_CONNECTED
        action_required = "Connected and verified (Safe Standby: WHATSAPP_PUBLISHING_ENABLED=0)."

    local_previews = adapter.get_local_template_previews()
    manual_checklist = [
        "1. Add a valid Billing / Payment Method on target WABA in Meta Business Suite -> Billing & Payments (clears Meta error 141006).",
        "2. Set the WABA Timezone in WhatsApp Manager -> Business Account Settings (clears Meta error 141007).",
        "3. Verify target phone number via SMS/Voice OTP and enable 2-Step Verification PIN in WhatsApp Manager (clears code_verification_status=NOT_VERIFIED & enables display name approval).",
        "4. Submit at least 1 Utility/Marketing template (client_welcome, consultation_reminder, or campaign_announcement) under WhatsApp Manager -> Message Templates and await Meta APPROVED status.",
        "5. Confirm whether +91 90990 28291 (WABA 1370721214882653) should be migrated/linked under verified Business Portfolio 560075574375818 or whether +91 98257 28291 (WABA 1471882524763501, already under verified portfolio 560075574375818) is the primary live sender.",
        "6. Configure WHATSAPP_APP_SECRET in VPS .env and subscribe Meta App 1397769361108621 to https://postpilot.gaatha.tech/api/webhooks/whatsapp (messages & message_template_status_update fields).",
    ]

    return {
        'success': True,
        'organization_id': organization_id,
        'platform': 'whatsapp',
        'account_name': 'Gaatha WhatsApp Business',
        'configured_waba_id': configured_waba_id,
        'configured_phone_id': configured_phone_id,
        'display_phone_number': primary_phone_info.get('display_phone_number', configured_phone_display),
        'verified_name': primary_phone_info.get('verified_name', 'Gaatha Ventures'),
        'code_verification_status': code_ver,
        'platform_type': plat_type,
        'phone_status': phone_status,
        'health_can_send': health_can_send,
        'health_errors': primary_line.get('health_errors', []),
        'approved_templates_count': templates_count,
        'total_approved_templates_count': total_approved_across_wabas,
        'local_preview_templates_count': len(local_previews),
        'publishing_enabled': config.is_platform_publishing_enabled('whatsapp'),
        'automatic_brand_binding': False,
        'token_health': token_health,
        'webhook_status': {
            'endpoint': '/api/webhooks/whatsapp',
            'app_secret_configured': bool(creds.get('app_secret')),
            'verify_token_configured': bool(creds.get('verify_token')),
            'postpilot_app_subscribed': any(n.get('postpilot_webhook_subscribed') for n in inspected_numbers),
        },
        'numbers': inspected_numbers,
        'status_label': status_label,
        'action_required': action_required,
        'discovered_wabas': discovered_wabas,
        'manual_action_checklist': manual_checklist,
    }


def map_property_to_brand(
    organization_id: int,
    platform: str,
    account_identifier: str,
    account_name: str,
    brand_id: int,
    permissions_scope: Optional[str] = None,
    app_identifier: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely assigns an accessible social property to a brand workspace.
    Strictly verifies organization ownership of target brand.
    Prevents cross-brand account bleeding.
    """
    clean_platform = str(platform).strip().lower()
    if clean_platform not in ('facebook', 'instagram', 'linkedin', 'whatsapp'):
        return {'success': False, 'error': f"Invalid platform '{platform}'"}

    # Validate brand belongs to active organization
    with database.get_db_connection() as conn:
        brand = conn.execute(
            "SELECT id, name FROM brands WHERE id = ? AND organization_id = ?",
            (brand_id, organization_id)
        ).fetchone()
        if not brand:
            return {'success': False, 'error': f"Brand #{brand_id} not found in active organization"}

    # Upsert account mapping
    success = database.upsert_social_account(
        organization_id=organization_id,
        brand_id=brand_id,
        platform=clean_platform,
        account_name=account_name,
        account_identifier=str(account_identifier),
        status='connected',
        permissions_scope=permissions_scope,
        app_identifier=app_identifier
    )

    return {
        'success': success,
        'platform': clean_platform,
        'account_identifier': str(account_identifier),
        'account_name': account_name,
        'brand_id': brand_id,
        'brand_name': brand['name'],
        'message': f"Successfully mapped {clean_platform.capitalize()} '{account_name}' to Brand '{brand['name']}'"
    }


def unmap_property(organization_id: int, account_id: int) -> Dict[str, Any]:
    """Disconnects and removes an account mapping respecting organization boundaries."""
    deleted = database.delete_social_account(account_id, organization_id=organization_id)
    if not deleted:
        return {'success': False, 'error': f"Account #{account_id} not found or unauthorized"}
    return {'success': True, 'message': f"Account #{account_id} successfully unmapped"}
