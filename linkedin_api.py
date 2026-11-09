"""
PostPilot LinkedIn Integration Module — Dual-Application Architecture
Provides secure, independent OAuth 2.0 authorization, member discovery, organization
permission validation, and organization post publishing for:
1. Aidni Global LLP (Org ID: 145240694)
2. Gaatha Ventures Sh.p.k. (Org ID: 145250613)

Zero credential disclosure, robust CSRF state protection, modern LinkedIn REST Posts API
compliance, and strict publishing safety guardrails.
"""
import os
import re
import json
import time
import hmac
import secrets
import logging
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any
import requests

import config

logger = logging.getLogger(__name__)

# LinkedIn API Endpoints
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REST_BASE_URL = "https://api.linkedin.com/v2"
REST_POSTS_URL = "https://api.linkedin.com/rest/posts"
REST_API_VERSION = "202401"

DEFAULT_TIMEOUT = 15  # seconds

# Confirmed Scopes currently available to both LinkedIn applications
CONFIRMED_SCOPES = [
    "openid",
    "profile",
    "email",
    "w_member_social"
]

# Community Management API Scopes required for Company Page management & publishing
COMMUNITY_MANAGEMENT_SCOPES = [
    "w_organization_social",
    "r_organization_social",
    "rw_organization_admin"
]

# Default requested scopes during authorization (Do NOT request unapproved products)
DEFAULT_SCOPES = CONFIRMED_SCOPES

# Application Identifier Constants
APP_AIDNI_GLOBAL = "aidni_global"
APP_GAATHA_VENTURES = "gaatha_ventures"
SUPPORTED_APPS = [APP_AIDNI_GLOBAL, APP_GAATHA_VENTURES]

# Default Organization IDs
DEFAULT_ORG_ID_AIDNI_GLOBAL = "145240694"
DEFAULT_ORG_ID_GAATHA_VENTURES = "145250613"

# Token persistence storage path inside data directory
TOKEN_STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TOKEN_STORE_FILE = os.path.join(TOKEN_STORE_DIR, "linkedin_tokens.json")

# In-memory runtime cache for tokens
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}


def normalize_app_key(app_key: Optional[str]) -> str:
    """Normalizes application identifiers into canonical app keys."""
    if not app_key:
        return APP_GAATHA_VENTURES
    cleaned = str(app_key).strip().lower().replace("-", "_").replace(" ", "_")
    if "aidni" in cleaned:
        return APP_AIDNI_GLOBAL
    if "gaatha" in cleaned:
        return APP_GAATHA_VENTURES
    return cleaned


def get_app_config(app_key: str) -> Dict[str, Any]:
    """
    Retrieves configuration for the specified LinkedIn application.
    Selects the exact Client ID, Client Secret, and Organization ID.
    Never exposes raw secrets in logs.
    """
    key = normalize_app_key(app_key)
    if key == APP_AIDNI_GLOBAL:
        cid = (
            getattr(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', None)
            or os.getenv('LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP')
            or os.getenv('LINKEDIN_CLIENT_ID_AIDNI_GLOBAL')
        )
        csec = (
            getattr(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', None)
            or os.getenv('LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP')
            or os.getenv('LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL')
        )
        env_token = (
            getattr(config, 'LINKEDIN_ACCESS_TOKEN_AIDNI_GLOBAL_LLP', None)
            or os.getenv('LINKEDIN_ACCESS_TOKEN_AIDNI_GLOBAL_LLP')
            or os.getenv('LINKEDIN_ACCESS_TOKEN_AIDNI_GLOBAL')
        )
        org_id = (
            getattr(config, 'LINKEDIN_ORG_ID_AIDNI_GLOBAL', None)
            or os.getenv('LINKEDIN_ORG_ID_AIDNI_GLOBAL')
            or DEFAULT_ORG_ID_AIDNI_GLOBAL
        )
        display_name = "Aidni Global LLP"

    elif key == APP_GAATHA_VENTURES:
        cid = (
            getattr(config, 'LINKEDIN_CLIENT_ID_GAATHA_VENTURES', None)
            or os.getenv('LINKEDIN_CLIENT_ID_GAATHA_VENTURES')
        )
        csec = (
            getattr(config, 'LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES', None)
            or os.getenv('LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES')
        )
        env_token = (
            getattr(config, 'LINKEDIN_ACCESS_TOKEN_GAATHA_VENTURES', None)
            or os.getenv('LINKEDIN_ACCESS_TOKEN_GAATHA_VENTURES')
        )
        org_id = (
            getattr(config, 'LINKEDIN_ORG_ID_GAATHA_VENTURES', None)
            or os.getenv('LINKEDIN_ORG_ID_GAATHA_VENTURES')
            or DEFAULT_ORG_ID_GAATHA_VENTURES
        )
        display_name = "Gaatha Ventures Sh.p.k."

    else:
        raise ValueError(f"Unsupported LinkedIn application: '{app_key}'. Supported: 'aidni_global', 'gaatha_ventures'")

    # Single-app fallback if dedicated app credentials are not yet set
    if not cid:
        cid = getattr(config, 'LINKEDIN_CLIENT_ID', None) or os.getenv('LINKEDIN_CLIENT_ID')
    if not csec:
        csec = getattr(config, 'LINKEDIN_CLIENT_SECRET', None) or os.getenv('LINKEDIN_CLIENT_SECRET')

    red_uri = (
        getattr(config, 'LINKEDIN_REDIRECT_URI', None)
        or os.getenv('LINKEDIN_REDIRECT_URI')
        or 'http://127.0.0.1:5000/api/auth/linkedin/callback'
    )

    clean_org_id = str(org_id).replace("urn:li:organization:", "").strip() if org_id else None

    return {
        'app_key': key,
        'display_name': display_name,
        'client_id': str(cid).strip() if cid else None,
        'client_secret': str(csec).strip() if csec else None,
        'redirect_uri': str(red_uri).strip(),
        'configured_token': str(env_token).strip() if env_token else None,
        'org_id': clean_org_id,
        'org_urn': f"urn:li:organization:{clean_org_id}" if clean_org_id else None
    }


def mask_secret_preview(secret: Optional[str]) -> str:
    """Safely masks credentials and tokens for diagnostic reporting."""
    if not secret:
        return "[NONE]"
    s = str(secret).strip()
    if len(s) <= 8:
        return "****"
    return f"{s[:4]}...{s[-4:]}"


def sanitize_log_message(msg: str) -> str:
    """Sanitizes sensitive tokens, secrets, and auth codes from log messages."""
    if not msg:
        return ""
    clean = str(msg)
    patterns = [
        r'(?i)(client_secret=)[^\s&"\']+',
        r'(?i)(access_token=)[^\s&"\']+',
        r'(?i)(code=)[^\s&"\']+',
        r'(?i)(bearer\s+)[^\s&"\']+',
        r'(?i)(token\s*:\s*["\'])[^\'"]+',
    ]
    for p in patterns:
        clean = re.sub(p, r'\1[REDACTED]', clean)
    return clean


# ==============================================================================
# Token Storage & Persistence Management
# ==============================================================================

def _load_token_store_from_disk() -> Dict[str, Any]:
    """Loads stored tokens from data/linkedin_tokens.json."""
    if not os.path.exists(TOKEN_STORE_FILE):
        return {}
    try:
        with open(TOKEN_STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read LinkedIn token store: {e}")
        return {}


def _write_token_store_to_disk(store: Dict[str, Any]) -> None:
    """Safely writes stored tokens to data/linkedin_tokens.json."""
    try:
        os.makedirs(TOKEN_STORE_DIR, exist_ok=True)
        with open(TOKEN_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to persist LinkedIn token store: {e}")


def save_token_data(app_key: str, token_data: Dict[str, Any]) -> None:
    """
    Saves access token and metadata for a specific LinkedIn application.
    Keeps each application's tokens completely isolated.
    """
    key = normalize_app_key(app_key)
    store = _load_token_store_from_disk()

    entry = {
        'app_key': key,
        'access_token': token_data.get('access_token'),
        'expires_in': token_data.get('expires_in', 0),
        'expires_at': token_data.get('expires_at') or (time.time() + token_data.get('expires_in', 0)),
        'scope': token_data.get('scope', ''),
        'token_type': token_data.get('token_type', 'Bearer'),
        'updated_at': time.time(),
        'member': token_data.get('member')
    }

    store[key] = entry
    _write_token_store_to_disk(store)
    _TOKEN_CACHE[key] = entry
    logger.info(f"Stored LinkedIn access token for application '{key}' (Expires in {int(entry['expires_in'])}s)")


def get_token_data(app_key: str) -> Optional[Dict[str, Any]]:
    """Retrieves stored token data for the specified application."""
    key = normalize_app_key(app_key)
    if key in _TOKEN_CACHE:
        return _TOKEN_CACHE[key]

    store = _load_token_store_from_disk()
    if key in store:
        _TOKEN_CACHE[key] = store[key]
        return store[key]

    # Fallback to .env configured token if present
    cfg = get_app_config(key)
    if cfg.get('configured_token'):
        static_entry = {
            'app_key': key,
            'access_token': cfg['configured_token'],
            'expires_in': 0,
            'expires_at': 0,  # Static token with unknown expiry
            'scope': ' '.join(CONFIRMED_SCOPES),
            'token_type': 'Bearer',
            'is_static_env': True
        }
        return static_entry

    return None


def is_token_expired(token_data: Optional[Dict[str, Any]]) -> bool:
    """Returns True if the token has expired, False otherwise."""
    if not token_data or not token_data.get('access_token'):
        return True
    expires_at = token_data.get('expires_at', 0)
    if expires_at and expires_at > 0:
        # Buffer of 60 seconds
        return time.time() >= (expires_at - 60)
    return False


def get_active_token(app_key: str) -> Optional[str]:
    """Retrieves an active (non-expired) access token for the specified application."""
    data = get_token_data(app_key)
    if not data or is_token_expired(data):
        return None
    return data.get('access_token')


# ==============================================================================
# OAuth 2.0 Authorization & Callback Handling
# ==============================================================================

def generate_oauth_state(app_key: str) -> Tuple[str, str]:
    """
    Generates a cryptographically strong random CSRF state token tied to the specific application.
    Format: '<app_key>:<csrf_token>'
    Returns:
        (state_string, csrf_token)
    """
    key = normalize_app_key(app_key)
    csrf = secrets.token_urlsafe(32)
    state = f"{key}:{csrf}"
    return state, csrf


def validate_oauth_state(state: Optional[str], expected_csrf: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates the OAuth state string received in the callback.
    Verifies that the state contains a valid app key and matching CSRF token.
    Returns:
        (is_valid, app_key, error_message)
    """
    if not state or not str(state).strip():
        return False, None, "Missing OAuth state parameter."

    parts = str(state).strip().split(":", 1)
    if len(parts) != 2:
        return False, None, "Invalid OAuth state format: missing application identifier."

    app_key, csrf = parts[0], parts[1]
    if app_key not in SUPPORTED_APPS:
        return False, None, f"Unrecognized application identifier in state: '{app_key}'."

    if expected_csrf:
        if not hmac.compare_digest(csrf, expected_csrf):
            return False, app_key, "CSRF state token mismatch."

    return True, app_key, None


def get_authorization_url(app_key: str = APP_GAATHA_VENTURES,
                           redirect_uri: Optional[str] = None,
                           state: Optional[str] = None,
                           scopes: Optional[List[str]] = None) -> Tuple[str, str, str]:
    """
    Constructs the LinkedIn OAuth 2.0 authorization URL for the specified application.
    Only requests confirmed available scopes by default.
    Returns:
        (authorization_url, state, csrf_token)
    Raises:
        ValueError if the application's Client ID is missing.
    """
    cfg = get_app_config(app_key)
    cid = cfg['client_id']
    if not cid:
        raise ValueError(
            f"Missing LinkedIn Client ID for {cfg['display_name']}. "
            f"Set LINKEDIN_CLIENT_ID_{cfg['app_key'].upper()} in .env."
        )

    red_uri = redirect_uri or cfg['redirect_uri']
    if not state:
        sec_state, csrf = generate_oauth_state(cfg['app_key'])
    else:
        sec_state = state
        csrf = state.split(":", 1)[1] if ":" in state else state

    requested_scopes = scopes or DEFAULT_SCOPES
    scope_str = " ".join(requested_scopes)

    params = {
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": red_uri,
        "state": sec_state,
        "scope": scope_str
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    logger.info(
        f"Generated LinkedIn OAuth authorization URL for {cfg['display_name']} "
        f"(Client: {mask_secret_preview(cid)}, State: {sec_state[:12]}...)"
    )
    return url, sec_state, csrf


def exchange_code_for_token(code: str,
                            app_key: str = APP_GAATHA_VENTURES,
                            redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """
    Exchanges an authorization code for an OAuth 2.0 access token using the specific
    application's Client ID and Secret.
    Stores the token securely and separately from other applications.
    """
    if not code or not str(code).strip():
        raise ValueError("Authorization code is required for token exchange.")

    cfg = get_app_config(app_key)
    cid = cfg['client_id']
    csecret = cfg['client_secret']

    if not cid:
        raise ValueError(f"Missing LinkedIn Client ID for {cfg['display_name']}.")
    if not csecret:
        raise ValueError(f"Missing LinkedIn Client Secret for {cfg['display_name']}.")

    red_uri = redirect_uri or cfg['redirect_uri']

    data = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": red_uri.strip(),
        "client_id": cid.strip(),
        "client_secret": csecret.strip()
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=DEFAULT_TIMEOUT)
        res_json = resp.json()
        if resp.status_code != 200:
            err_msg = res_json.get('error_description') or res_json.get('error') or 'Token exchange failed'
            logger.error(f"LinkedIn token exchange rejected for {cfg['display_name']}: {sanitize_log_message(str(err_msg))}")
            return {
                'success': False,
                'app_key': cfg['app_key'],
                'error': str(err_msg),
                'status_code': resp.status_code
            }

        token = res_json.get('access_token')
        expires_in = res_json.get('expires_in', 0)
        scope = res_json.get('scope', '')

        # Fetch authenticated member profile
        member = get_authenticated_member(token)

        token_record = {
            'access_token': token,
            'expires_in': expires_in,
            'expires_at': time.time() + expires_in,
            'scope': scope,
            'token_type': res_json.get('token_type', 'Bearer'),
            'member': member if member.get('success') else None
        }

        # Save independently for this application
        save_token_data(cfg['app_key'], token_record)

        logger.info(
            f"LinkedIn token exchange successful for {cfg['display_name']}. "
            f"Token preview: {mask_secret_preview(token)} (Expires in {expires_in}s)"
        )

        return {
            'success': True,
            'app_key': cfg['app_key'],
            'display_name': cfg['display_name'],
            'access_token': token,
            'expires_in': expires_in,
            'scope': scope,
            'member': member if member.get('success') else None
        }

    except Exception as e:
        safe_e = sanitize_log_message(str(e))
        logger.error(f"Network error exchanging LinkedIn authorization code for {cfg['display_name']}: {safe_e}")
        return {'success': False, 'app_key': cfg['app_key'], 'error': safe_e}


# ==============================================================================
# Member Profile & Organization Permissions
# ==============================================================================

def get_authenticated_member(access_token: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves profile information for the authenticated member via /v2/userinfo."""
    if not access_token:
        return {'success': False, 'error': 'Missing LinkedIn access token.'}

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(f"{REST_BASE_URL}/userinfo", headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'success': True,
                'sub': data.get('sub'),
                'name': data.get('name'),
                'given_name': data.get('given_name'),
                'family_name': data.get('family_name'),
                'email': data.get('email'),
                'picture': data.get('picture')
            }
        else:
            return {'success': False, 'error': sanitize_log_message(resp.text), 'status_code': resp.status_code}
    except Exception as e:
        return {'success': False, 'error': sanitize_log_message(str(e))}


def check_organization_publishing_eligibility(app_key: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifies the authenticated member's permissions and Community Management API status.
    Clearly distinguishes:
    1. Personal LinkedIn posting available (w_member_social).
    2. Company-page publishing unavailable because Community Management API access has not been approved.
    3. Company-page publishing authorized.
    """
    cfg = get_app_config(app_key)
    token = access_token or get_active_token(cfg['app_key'])
    token_data = get_token_data(cfg['app_key'])

    if not token:
        return {
            'app_key': cfg['app_key'],
            'display_name': cfg['display_name'],
            'authenticated': False,
            'personal_posting_available': False,
            'company_publishing_authorized': False,
            'eligibility_code': 'UNAUTHENTICATED',
            'eligibility_message': 'Authentication required. Connect this LinkedIn application via OAuth.',
            'org_id': cfg['org_id'],
            'org_urn': cfg['org_urn']
        }

    granted_scopes = (token_data.get('scope', '') or '').split() if token_data else []
    # If scopes not recorded, assume confirmed scopes
    if not granted_scopes:
        granted_scopes = CONFIRMED_SCOPES

    has_member_social = 'w_member_social' in granted_scopes
    has_org_social = 'w_organization_social' in granted_scopes

    # Case 1: Only member social scopes are approved
    if not has_org_social:
        return {
            'app_key': cfg['app_key'],
            'display_name': cfg['display_name'],
            'authenticated': True,
            'personal_posting_available': has_member_social,
            'company_publishing_authorized': False,
            'eligibility_code': 'COMMUNITY_MANAGEMENT_API_REQUIRED',
            'eligibility_message': (
                f"Personal LinkedIn posting available (w_member_social). "
                f"Company-page publishing unavailable: Community Management API access has not been approved "
                f"for {cfg['display_name']}."
            ),
            'org_id': cfg['org_id'],
            'org_urn': cfg['org_urn'],
            'granted_scopes': granted_scopes,
            'required_scopes': ['w_organization_social', 'rw_organization_admin']
        }

    # Case 2: Community Management API scopes present, verify ACL admin role
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    url = f"{REST_BASE_URL}/organizationalEntityAcls?q=roleAssignee"

    try:
        resp = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            return {
                'app_key': cfg['app_key'],
                'display_name': cfg['display_name'],
                'authenticated': True,
                'personal_posting_available': has_member_social,
                'company_publishing_authorized': False,
                'eligibility_code': 'COMMUNITY_MANAGEMENT_API_DENIED',
                'eligibility_message': f"LinkedIn returned HTTP {resp.status_code} querying organization ACLs.",
                'org_id': cfg['org_id'],
                'org_urn': cfg['org_urn'],
                'granted_scopes': granted_scopes
            }

        elements = resp.json().get('elements', [])
        target_urn = cfg['org_urn']
        is_admin = False

        for acl in elements:
            if acl.get('organizationalTarget') == target_urn and acl.get('state') == 'APPROVED':
                role = acl.get('role')
                if role in ('ADMINISTRATOR', 'DIRECT_SPONSORED_CONTENT_POSTER', 'CURATOR'):
                    is_admin = True
                    break

        if is_admin:
            return {
                'app_key': cfg['app_key'],
                'display_name': cfg['display_name'],
                'authenticated': True,
                'personal_posting_available': True,
                'company_publishing_authorized': True,
                'eligibility_code': 'AUTHORIZED',
                'eligibility_message': f"Company-page publishing authorized for {cfg['display_name']}.",
                'org_id': cfg['org_id'],
                'org_urn': cfg['org_urn'],
                'granted_scopes': granted_scopes
            }
        else:
            return {
                'app_key': cfg['app_key'],
                'display_name': cfg['display_name'],
                'authenticated': True,
                'personal_posting_available': True,
                'company_publishing_authorized': False,
                'eligibility_code': 'NOT_ORGANIZATION_ADMIN',
                'eligibility_message': f"Authenticated member is not an Administrator of {cfg['display_name']} on LinkedIn.",
                'org_id': cfg['org_id'],
                'org_urn': cfg['org_urn'],
                'granted_scopes': granted_scopes
            }

    except Exception as e:
        safe_e = sanitize_log_message(str(e))
        return {
            'app_key': cfg['app_key'],
            'display_name': cfg['display_name'],
            'authenticated': True,
            'personal_posting_available': has_member_social,
            'company_publishing_authorized': False,
            'eligibility_code': 'ERROR',
            'eligibility_message': f"Error validating organization permissions: {safe_e}",
            'org_id': cfg['org_id'],
            'org_urn': cfg['org_urn']
        }


def audit_linkedin_status() -> Dict[str, Any]:
    """
    Audits connection status, member identity, organization discovery,
    and publishing readiness for BOTH LinkedIn applications.
    Zero secret exposure.
    """
    apps_status = {}
    for app_key in SUPPORTED_APPS:
        cfg = get_app_config(app_key)
        has_client_id = bool(cfg['client_id'])
        has_client_secret = bool(cfg['client_secret'])
        token_data = get_token_data(app_key)
        token = token_data.get('access_token') if token_data else None
        expired = is_token_expired(token_data)

        # Eligibility check
        eligibility = check_organization_publishing_eligibility(app_key, access_token=token)

        member_info = None
        if token and not expired:
            if token_data and token_data.get('member'):
                member_info = token_data['member']
            else:
                m = get_authenticated_member(token)
                if m.get('success'):
                    member_info = {'name': m.get('name'), 'sub': m.get('sub'), 'email': m.get('email')}

        apps_status[app_key] = {
            'app_key': app_key,
            'display_name': cfg['display_name'],
            'configured': has_client_id and has_client_secret,
            'has_client_id': has_client_id,
            'has_client_secret': has_client_secret,
            'authenticated': bool(token and not expired),
            'is_token_expired': expired,
            'token_preview': mask_secret_preview(token),
            'token_expiry': token_data.get('expires_at') if token_data else None,
            'token_expires_in': int(max(0, (token_data.get('expires_at', 0) - time.time()))) if token_data and token_data.get('expires_at') else 0,
            'org_id': cfg['org_id'],
            'org_urn': cfg['org_urn'],
            'member': member_info,
            'personal_posting_available': eligibility.get('personal_posting_available', False),
            'company_publishing_authorized': eligibility.get('company_publishing_authorized', False),
            'eligibility_code': eligibility.get('eligibility_code'),
            'eligibility_message': eligibility.get('eligibility_message'),
            'connect_url': f"/api/auth/linkedin/connect?app={app_key}"
        }

    return {
        'apps': apps_status,
        'publishing_enabled': config.is_publishing_enabled(),
        # Backwards compatibility top-level aliases
        'configured': all(a['configured'] for a in apps_status.values()),
        'authenticated': any(a['authenticated'] for a in apps_status.values()),
        'targets': {
            'aidni_global': apps_status[APP_AIDNI_GLOBAL],
            'gaatha_ventures': apps_status[APP_GAATHA_VENTURES]
        }
    }


# ==============================================================================
# LinkedIn REST Posts API (Modern Endpoint)
# ==============================================================================

def create_organization_post(organization_id: str,
                             text: str,
                             app_key: Optional[str] = None,
                             access_token: Optional[str] = None,
                             image_urn: Optional[str] = None) -> Dict[str, Any]:
    """
    Creates a post on LinkedIn for an organization using the modern REST Posts API.
    Endpoint: POST https://api.linkedin.com/rest/posts
    Headers: LinkedIn-Version: 202401, X-Restli-Protocol-Version: 2.0.0

    Publishing Safety:
        When POSTPILOT_PUBLISHING_ENABLED=0, strictly blocks external network calls
        and returns a safe simulated response.
    """
    if not organization_id or not str(organization_id).strip():
        raise ValueError("Organization ID is required to create a LinkedIn organization post.")
    if not text or not str(text).strip():
        raise ValueError("Post text cannot be empty.")

    clean_org_id = str(organization_id).replace("urn:li:organization:", "").strip()

    # Determine which application config applies
    resolved_app = normalize_app_key(app_key) if app_key else None
    if not resolved_app:
        if clean_org_id == DEFAULT_ORG_ID_AIDNI_GLOBAL:
            resolved_app = APP_AIDNI_GLOBAL
        else:
            resolved_app = APP_GAATHA_VENTURES

    # Publishing Safety Guardrail
    if not config.is_publishing_enabled():
        logger.info(
            f"🛡️ [SAFETY] LinkedIn organization publishing blocked/simulated (POSTPILOT_PUBLISHING_ENABLED=0): "
            f"Organization ID {clean_org_id} (App: {resolved_app})"
        )
        sim_id = f"urn:li:share:sim_{int(time.time() * 1000)}"
        return {
            'id': sim_id,
            'share_urn': sim_id,
            'organization_id': clean_org_id,
            'app_key': resolved_app,
            'simulated': True,
            'success': True,
            'image_urn': image_urn,
            'message': 'Simulated publishing: POSTPILOT_PUBLISHING_ENABLED is 0'
        }

    token = access_token or get_active_token(resolved_app)
    if not token:
        logger.error(f"Cannot publish LinkedIn post for org {clean_org_id}: Missing access token for {resolved_app}.")
        return {'success': False, 'error': f"Missing LinkedIn access token for application '{resolved_app}'."}

    # Modern LinkedIn REST Posts API
    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": REST_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    payload = {
        "author": f"urn:li:organization:{clean_org_id}",
        "commentary": str(text).strip(),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False
    }

    if image_urn:
        payload["content"] = {
            "media": {
                "id": image_urn
            }
        }

    try:
        resp = requests.post(REST_POSTS_URL, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code in (200, 201):
            post_urn = resp.headers.get('x-restli-id') or resp.headers.get('X-RestLi-Id')
            if not post_urn:
                try:
                    data = resp.json()
                    post_urn = data.get('id') or data.get('urn')
                except Exception:
                    post_urn = f"urn:li:share:{clean_org_id}_{int(time.time())}"

            logger.info(f"Successfully published LinkedIn post {post_urn} for organization {clean_org_id}")
            return {
                'success': True,
                'id': post_urn,
                'share_urn': post_urn,
                'organization_id': clean_org_id,
                'app_key': resolved_app
            }
        elif resp.status_code == 403:
            err = sanitize_log_message(resp.text)
            logger.error(
                f"LinkedIn REST Posts API 403 Forbidden for org {clean_org_id}: "
                f"Requires approved Community Management API (w_organization_social). Details: {err}"
            )
            return {
                'success': False,
                'status_code': 403,
                'error': (
                    "Organization publishing unauthorized (HTTP 403). "
                    "Community Management API (w_organization_social) access is required to publish to company pages."
                ),
                'details': err
            }
        else:
            err = sanitize_log_message(resp.text)
            logger.error(f"LinkedIn REST Posts API rejected (HTTP {resp.status_code}): {err}")
            return {
                'success': False,
                'status_code': resp.status_code,
                'error': err
            }
    except Exception as e:
        safe_e = sanitize_log_message(str(e))
        logger.error(f"Exception publishing to LinkedIn organization {clean_org_id}: {safe_e}")
        return {'success': False, 'error': safe_e}


# ==============================================================================
# LinkedIn REST Media Upload Procedures (Phase 2)
# ==============================================================================

def initialize_image_upload(organization_id: str,
                            app_key: Optional[str] = None,
                            access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Step 1: Initializes an image upload request on LinkedIn modern REST API.
    POST https://api.linkedin.com/rest/images?action=initializeUpload
    """
    clean_org_id = str(organization_id).replace("urn:li:organization:", "").strip()
    resolved_app = normalize_app_key(app_key) if app_key else APP_GAATHA_VENTURES

    if not config.is_publishing_enabled():
        return {
            'success': True,
            'upload_url': f"https://api.linkedin.com/mediaUpload/simulated_{int(time.time())}",
            'image_urn': f"urn:li:image:sim_{int(time.time() * 1000)}",
            'simulated': True
        }

    token = access_token or get_active_token(resolved_app)
    if not token:
        return {'success': False, 'error': f"Missing access token for {resolved_app}."}

    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": REST_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    payload = {
        "initializeUploadRequest": {
            "owner": f"urn:li:organization:{clean_org_id}"
        }
    }
    try:
        resp = requests.post(
            "https://api.linkedin.com/rest/images?action=initializeUpload",
            json=payload,
            headers=headers,
            timeout=DEFAULT_TIMEOUT
        )
        if resp.status_code in (200, 201):
            val = resp.json().get('value', {})
            return {
                'success': True,
                'upload_url': val.get('uploadUrl'),
                'image_urn': val.get('image'),
                'simulated': False
            }
        err = sanitize_log_message(resp.text)
        return {'success': False, 'error': f"LinkedIn image initializeUpload failed: {err}"}
    except Exception as e:
        return {'success': False, 'error': sanitize_log_message(str(e))}


def upload_image_file(upload_url: str, file_path: str, access_token: Optional[str] = None) -> bool:
    """
    Step 2: Uploads raw image binary to the designated LinkedIn uploadUrl.
    PUT {upload_url}
    """
    if not config.is_publishing_enabled() or 'simulated' in upload_url:
        return True

    if not os.path.isfile(file_path):
        return False

    try:
        with open(file_path, 'rb') as f:
            data = f.read()

        headers = {"Content-Type": "application/octet-stream"}
        resp = requests.put(upload_url, data=data, headers=headers, timeout=DEFAULT_TIMEOUT)
        return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Error uploading image binary to LinkedIn: {sanitize_log_message(str(e))}")
        return False
