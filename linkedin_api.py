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

# LinkedIn API Endpoints & Centralized Version
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REST_BASE_URL = "https://api.linkedin.com/v2"
REST_POSTS_URL = "https://api.linkedin.com/rest/posts"
REST_API_VERSION = getattr(config, 'LINKEDIN_API_VERSION', '202610')


def get_rest_api_version() -> str:
    """Returns centralized active LinkedIn REST API YYYYMM version (non-sunset)."""
    return (os.getenv('LINKEDIN_API_VERSION') or getattr(config, 'LINKEDIN_API_VERSION', '202610') or '202610').strip()

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

# Per-app verified scope profiles:
# - Aidni Global LLP: Sign In with LinkedIn using OpenID Connect + Share on LinkedIn
# - Gaatha Ventures Sh.p.k.: Share on LinkedIn (w_member_social) unless OpenID/Community Management are explicitly approved
DEFAULT_SCOPES_BY_APP = {
    "aidni_global": list(CONFIRMED_SCOPES),
    "gaatha_ventures": ["w_member_social"],
}


def parse_scopes(scope_value):
    """Splits LinkedIn space- or comma-separated scope strings/iterables into an ordered unique list."""
    if not scope_value:
        return []
    if isinstance(scope_value, (list, tuple, set)):
        raw_items = []
        for item in scope_value:
            raw_items.extend(str(item).replace(",", " ").split())
    else:
        raw_items = str(scope_value).replace(",", " ").split()
    seen = set()
    parsed = []
    for item in raw_items:
        clean = item.strip()
        if clean and clean not in seen:
            seen.add(clean)
            parsed.append(clean)
    return parsed


def get_default_scopes(app_key=None):
    """
    Returns default authorized OAuth scopes for the given LinkedIn application.
    Supports optional environment overrides:
      - LINKEDIN_SCOPES_AIDNI_GLOBAL
      - LINKEDIN_SCOPES_GAATHA_VENTURES
    """
    import os
    norm_key = normalize_app_key(app_key)
    env_var = (
        "LINKEDIN_SCOPES_AIDNI_GLOBAL"
        if norm_key == "aidni_global"
        else "LINKEDIN_SCOPES_GAATHA_VENTURES"
    )
    override = (os.environ.get(env_var) or "").strip()
    if override:
        parsed = parse_scopes(override)
        if parsed:
            return parsed
    return list(DEFAULT_SCOPES_BY_APP.get(norm_key, DEFAULT_SCOPES))


def introspect_token(app_key=None, access_token=None):
    """
    Verifies a LinkedIn OAuth access token via LinkedIn's token introspection endpoint
    (works for w_member_social-only tokens without requiring OpenID /v2/userinfo scopes).
    """
    import logging
    cfg = get_app_config(app_key)
    token = access_token or get_active_token(cfg['app_key'])
    if not token:
        return {
            'checked': False,
            'active': False,
            'scopes': [],
            'error': 'No active token available for introspection.',
        }
    if not cfg.get('client_id') or not cfg.get('client_secret'):
        return {
            'checked': False,
            'active': False,
            'scopes': [],
            'error': 'Client credentials not configured for introspection.',
        }
    try:
        resp = requests.post(
            "https://www.linkedin.com/oauth/v2/introspectToken",
            data={
                'client_id': cfg['client_id'],
                'client_secret': cfg['client_secret'],
                'token': token,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json() or {}
            scopes = parse_scopes(data.get('scope'))
            return {
                'checked': True,
                'active': bool(data.get('active')),
                'status': data.get('status'),
                'scope': data.get('scope', ''),
                'scopes': scopes,
                'auth_type': data.get('auth_type'),
                'exp': data.get('exp'),
            }
        return {
            'checked': False,
            'active': False,
            'scopes': [],
            'error': f"HTTP {resp.status_code}",
        }
    except Exception as e:
        safe_err = sanitize_log_message(str(e))
        logging.getLogger('App').warning(
            f"LinkedIn token introspection error for {cfg['app_key']}: {safe_err}"
        )
        return {
            'checked': False,
            'active': False,
            'scopes': [],
            'error': safe_err,
        }

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

    # Never cross-contaminate credentials across apps via config backward-compatibility aliases.
    if not cid:
        cid = os.getenv('LINKEDIN_CLIENT_ID')
    if not csec:
        csec = os.getenv('LINKEDIN_CLIENT_SECRET')

    red_uri = (
        getattr(config, 'LINKEDIN_REDIRECT_URI', None)
        or os.getenv('LINKEDIN_REDIRECT_URI')
        or 'https://postpilot.gaatha.tech/api/auth/linkedin/callback'
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
    """Sanitizes sensitive tokens, secrets, refresh tokens, and auth codes from log messages."""
    if not msg:
        return ""
    clean = str(msg)
    patterns = [
        r'(?i)(client_secret=)[^\s&"\']+',
        r'(?i)(access_token=)[^\s&"\']+',
        r'(?i)(refresh_token=)[^\s&"\']+',
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
    """Safely writes stored tokens to data/linkedin_tokens.json with restrictive permissions."""
    try:
        os.makedirs(TOKEN_STORE_DIR, exist_ok=True)
        with open(TOKEN_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
        if os.name == 'posix':
            os.chmod(TOKEN_STORE_FILE, 0o600)
    except Exception as e:
        logger.error(f"Failed to persist LinkedIn token store: {sanitize_log_message(str(e))}")


def save_token_data(app_key: str, token_data: Dict[str, Any]) -> None:
    """
    Saves access token and optional refresh metadata for a specific LinkedIn application.
    Keeps each application's tokens completely isolated.
    """
    key = normalize_app_key(app_key)
    store = _load_token_store_from_disk()
    existing = store.get(key, {}) if isinstance(store.get(key), dict) else {}

    entry = {
        'app_key': key,
        'access_token': token_data.get('access_token'),
        'expires_in': token_data.get('expires_in', 0),
        'expires_at': token_data.get('expires_at') or (time.time() + token_data.get('expires_in', 0)),
        'scope': token_data.get('scope', ''),
        'token_type': token_data.get('token_type', 'Bearer'),
        'updated_at': time.time(),
        'member': token_data.get('member') if token_data.get('member') is not None else existing.get('member'),
    }
    if token_data.get('refresh_token'):
        entry['refresh_token'] = token_data['refresh_token']
        r_exp_in = token_data.get('refresh_token_expires_in', 0)
        entry['refresh_token_expires_in'] = r_exp_in
        entry['refresh_token_expires_at'] = token_data.get('refresh_token_expires_at') or (time.time() + r_exp_in if r_exp_in else 0)
    elif existing.get('refresh_token') and token_data.get('preserve_refresh_token', True):
        entry['refresh_token'] = existing['refresh_token']
        entry['refresh_token_expires_in'] = existing.get('refresh_token_expires_in', 0)
        entry['refresh_token_expires_at'] = existing.get('refresh_token_expires_at', 0)

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


def refresh_access_token(app_key: str) -> Dict[str, Any]:
    """
    Refreshes a LinkedIn OAuth token ONLY if the app has an authorized non-expired refresh_token.
    Never overwrites or invalidates the existing stored token unless the replacement token
    is returned and verified active.
    """
    key = normalize_app_key(app_key)
    cfg = get_app_config(key)
    td = get_token_data(key) or {}
    ref_tok = (td.get('refresh_token') or '').strip()
    if not ref_tok:
        return {
            'success': False,
            'app_key': key,
            'refresh_supported': False,
            'reauth_required': True,
            'error': f"Programmatic refresh_token not available for '{cfg['display_name']}'. Re-authorization via OAuth is required.",
        }

    ref_exp = td.get('refresh_token_expires_at') or 0
    if ref_exp and float(ref_exp) > 0 and time.time() >= (float(ref_exp) - 60):
        return {
            'success': False,
            'app_key': key,
            'refresh_supported': True,
            'reauth_required': True,
            'error': f"Refresh token for '{cfg['display_name']}' has expired. Re-authorization via OAuth is required.",
        }

    if not cfg.get('client_id') or not cfg.get('client_secret'):
        return {'success': False, 'app_key': key, 'reauth_required': True, 'error': 'Missing client credentials.'}

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': ref_tok,
                'client_id': cfg['client_id'],
                'client_secret': cfg['client_secret'],
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=DEFAULT_TIMEOUT,
        )
        res_json = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
        new_token = (res_json.get('access_token') or '').strip()
        if resp.status_code != 200 or not new_token:
            err = sanitize_log_message(res_json.get('error_description') or res_json.get('error') or f"HTTP {resp.status_code}")
            return {'success': False, 'app_key': key, 'refresh_supported': True, 'reauth_required': True, 'error': err}

        # Verify replacement token before replacing stored credential
        intr = introspect_token(key, access_token=new_token)
        if intr.get('checked') and not intr.get('active'):
            return {'success': False, 'app_key': key, 'reauth_required': True, 'error': 'Replacement token failed active verification; existing token preserved.'}

        expires_in = res_json.get('expires_in', 0)
        new_record = {
            'access_token': new_token,
            'expires_in': expires_in,
            'expires_at': time.time() + expires_in if expires_in else 0,
            'scope': res_json.get('scope') or ' '.join(intr.get('scopes') or []) or td.get('scope', ''),
            'token_type': res_json.get('token_type', 'Bearer'),
            'refresh_token': res_json.get('refresh_token') or ref_tok,
            'refresh_token_expires_in': res_json.get('refresh_token_expires_in') or td.get('refresh_token_expires_in', 0),
        }
        save_token_data(key, new_record)
        return {'success': True, 'app_key': key, 'expires_in': expires_in, 'scope': new_record['scope']}
    except Exception as e:
        return {'success': False, 'app_key': key, 'reauth_required': True, 'error': sanitize_log_message(str(e))}


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

    if scopes is None:
        requested_scopes = get_default_scopes(cfg['app_key'])
    else:
        requested_scopes = parse_scopes(scopes) or get_default_scopes(cfg['app_key'])
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

        # Fetch authenticated member profile only when OpenID scopes are granted
        granted_scopes = parse_scopes(scope)
        if 'openid' in granted_scopes and 'profile' in granted_scopes:
            member = get_authenticated_member(token)
        else:
            member = {'success': False, 'skipped': True}

        token_record = {
            'access_token': token,
            'expires_in': expires_in,
            'expires_at': time.time() + expires_in,
            'scope': scope,
            'token_type': res_json.get('token_type', 'Bearer'),
            'member': member if member.get('success') else None,
            'preserve_refresh_token': False,
        }
        if res_json.get('refresh_token'):
            token_record['refresh_token'] = res_json.get('refresh_token')
            token_record['refresh_token_expires_in'] = res_json.get('refresh_token_expires_in', 0)

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
            'expires_at': token_record['expires_at'],
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
            sub = data.get('sub')
            return {
                'success': True,
                'sub': sub,
                'author_urn': f"urn:li:person:{sub}" if sub else None,
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


def resolve_member_author(app_key: str, access_token: Optional[str] = None, verify_live: bool = True) -> Dict[str, Any]:
    """
    Resolves verified member author URN ('urn:li:person:<sub>') via LinkedIn identity endpoint
    without ever guessing or constructing a member ID.
    Requires active non-expired token, w_member_social, and identity access (/v2/userinfo).
    """
    cfg = get_app_config(app_key)
    key = cfg['app_key']
    td = get_token_data(key) or {}
    tok = access_token or td.get('access_token')
    if not tok:
        return {'success': False, 'app_key': key, 'error_code': 'UNAUTHENTICATED', 'error': f"Missing access token for '{cfg['display_name']}'."}

    if not access_token and is_token_expired(td):
        return {'success': False, 'app_key': key, 'error_code': 'TOKEN_EXPIRED', 'error': f"Access token expired for '{cfg['display_name']}'. Re-authorization required."}

    scopes = parse_scopes(td.get('scope'))
    if verify_live and cfg.get('client_id') and cfg.get('client_secret'):
        intr = introspect_token(key, access_token=tok)
        if intr.get('checked'):
            if not intr.get('active'):
                return {'success': False, 'app_key': key, 'error_code': 'TOKEN_EXPIRED', 'error': f"Token is inactive/revoked for '{cfg['display_name']}'. Re-authorization required."}
            if intr.get('scopes'):
                scopes = intr['scopes']

    if scopes and 'w_member_social' not in scopes:
        return {
            'success': False,
            'app_key': key,
            'error_code': 'MISSING_W_MEMBER_SOCIAL',
            'scopes': scopes,
            'error': f"Token for '{cfg['display_name']}' lacks required 'w_member_social' permission.",
        }

    cached_member = td.get('member') if isinstance(td.get('member'), dict) else None
    if cached_member and cached_member.get('sub') and not verify_live:
        sub = str(cached_member['sub']).strip()
        return {
            'success': True,
            'app_key': key,
            'member_id': sub,
            'author_urn': f"urn:li:person:{sub}",
            'member': cached_member,
            'scopes': scopes,
        }

    # Verify against /v2/userinfo when OpenID scopes exist (or live check is requested)
    if not scopes or ('openid' in scopes and 'profile' in scopes) or verify_live:
        ui = get_authenticated_member(tok)
        if ui.get('success') and ui.get('sub'):
            sub = str(ui['sub']).strip()
            member_clean = {'sub': sub, 'author_urn': f"urn:li:person:{sub}", 'name': ui.get('name'), 'email': ui.get('email')}
            return {
                'success': True,
                'app_key': key,
                'member_id': sub,
                'author_urn': f"urn:li:person:{sub}",
                'member': member_clean,
                'scopes': scopes,
            }
        status_c = ui.get('status_code')
        if status_c == 401:
            return {'success': False, 'app_key': key, 'error_code': 'TOKEN_EXPIRED', 'scopes': scopes, 'error': 'LinkedIn rejected token (HTTP 401); re-authorization required.'}
        if status_c == 403 or ('openid' not in scopes or 'profile' not in scopes):
            return {
                'success': False,
                'app_key': key,
                'error_code': 'IDENTITY_SCOPE_REQUIRED',
                'scopes': scopes,
                'error': f"Cannot resolve LinkedIn member URN for '{cfg['display_name']}': OpenID Connect ('openid profile') permission is missing on this token.",
            }
        return {'success': False, 'app_key': key, 'error_code': 'IDENTITY_LOOKUP_FAILED', 'scopes': scopes, 'error': ui.get('error') or 'Failed to resolve member identity.'}

    return {
        'success': False,
        'app_key': key,
        'error_code': 'IDENTITY_SCOPE_REQUIRED',
        'scopes': scopes,
        'error': f"Cannot verify member author URN for '{cfg['display_name']}' without 'openid' and 'profile' scopes.",
    }


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

    granted_scopes = parse_scopes(token_data.get('scope', '')) if token_data else []
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
        "LinkedIn-Version": get_rest_api_version(),
        "X-Restli-Protocol-Version": "2.0.0"
    }
    url = "https://api.linkedin.com/rest/organizationAcls?q=roleAssignee&role=ADMINISTRATOR&state=APPROVED"

    try:
        resp = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 426:
            resp = requests.get(f"{REST_BASE_URL}/organizationalEntityAcls?q=roleAssignee", headers=headers, timeout=DEFAULT_TIMEOUT)
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
            target = acl.get('organizationalTarget') or acl.get('organization')
            if target == target_urn and acl.get('state') == 'APPROVED':
                role = acl.get('role')
                if role in ('ADMINISTRATOR', 'DIRECT_SPONSORED_CONTENT_POSTER', 'CURATOR', 'CONTENT_ADMIN'):
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


def audit_linkedin_status(verify_live: bool = False) -> Dict[str, Any]:
    """
    Audits connection status, member identity, organization discovery,
    refresh lifecycle, and destination readiness for BOTH LinkedIn applications.
    Zero secret exposure.
    """
    apps_status = {}
    api_ver = get_rest_api_version()
    personal_flag_enabled = config.is_linkedin_personal_publishing_enabled()
    company_flag_enabled = config.is_linkedin_company_publishing_enabled()

    for app_key in SUPPORTED_APPS:
        cfg = get_app_config(app_key)
        has_client_id = bool(cfg['client_id'])
        has_client_secret = bool(cfg['client_secret'])
        token_data = get_token_data(app_key)
        token = token_data.get('access_token') if token_data else None
        expired = is_token_expired(token_data)
        has_refresh = bool(token_data and token_data.get('refresh_token'))

        eligibility = check_organization_publishing_eligibility(app_key, access_token=token if not expired else None)
        granted_scopes = parse_scopes(token_data.get('scope')) if token_data else []

        member_info = None
        identity_res: Dict[str, Any] = {'success': False}
        if token and not expired:
            if token_data and isinstance(token_data.get('member'), dict) and token_data['member'].get('sub') and not verify_live:
                member_info = token_data['member']
                identity_res = {
                    'success': True,
                    'author_urn': member_info.get('author_urn') or f"urn:li:person:{member_info['sub']}",
                    'member': member_info,
                }
            elif ('openid' in granted_scopes and 'profile' in granted_scopes) or verify_live:
                identity_res = resolve_member_author(app_key, access_token=token, verify_live=verify_live)
                if identity_res.get('success'):
                    member_info = identity_res.get('member')
            else:
                identity_res = {
                    'success': False,
                    'error_code': 'IDENTITY_SCOPE_REQUIRED',
                    'error': "Missing 'openid profile' scope to verify member identity.",
                }

        has_w_member = 'w_member_social' in granted_scopes
        identity_verified = bool(identity_res.get('success') and member_info and (member_info.get('sub') or identity_res.get('author_urn')))
        personal_ready = bool(token and not expired and has_w_member and identity_verified and personal_flag_enabled)
        org_ready = bool(eligibility.get('company_publishing_authorized', False) and company_flag_enabled)

        apps_status[app_key] = {
            'app_key': app_key,
            'display_name': cfg['display_name'],
            'configured': has_client_id and has_client_secret,
            'has_client_id': has_client_id,
            'has_client_secret': has_client_secret,
            'authenticated': bool(token and not expired),
            'is_token_expired': expired,
            'reauth_required': bool(not token or expired),
            'refresh_token_available': has_refresh,
            'refresh_token_expires_at': token_data.get('refresh_token_expires_at') if token_data else None,
            'token_preview': mask_secret_preview(token),
            'token_expiry': token_data.get('expires_at') if token_data else None,
            'token_expires_in': int(max(0, (token_data.get('expires_at', 0) - time.time()))) if token_data and token_data.get('expires_at') else 0,
            'org_id': cfg['org_id'],
            'org_urn': cfg['org_urn'],
            'member': member_info,
            'member_identity_verified': identity_verified,
            'author_urn': identity_res.get('author_urn') if identity_verified else None,
            'identity_error_code': None if identity_verified else identity_res.get('error_code'),
            'scopes': granted_scopes,
            'requested_scopes': get_default_scopes(app_key),
            'personal_posting_available': bool(token and not expired and has_w_member and (identity_verified or 'openid' in granted_scopes)),
            'personal_publishing_ready': personal_ready,
            'company_publishing_authorized': eligibility.get('company_publishing_authorized', False),
            'company_publishing_ready': org_ready,
            'eligibility_code': eligibility.get('eligibility_code'),
            'eligibility_message': eligibility.get('eligibility_message'),
            'connect_url': f"/api/auth/linkedin/connect?app={app_key}"
        }

    aidni = apps_status[APP_AIDNI_GLOBAL]
    gaatha = apps_status[APP_GAATHA_VENTURES]

    destinations = [
        {
            'key': 'personal:aidni_global',
            'destination_type': 'personal',
            'app_key': APP_AIDNI_GLOBAL,
            'label': f"Personal LinkedIn Profile ({(aidni.get('member') or {}).get('name') or 'LinkedIn Member'})",
            'author_urn': aidni.get('author_urn'),
            'connected': aidni['authenticated'],
            'read_identity_verified': aidni['member_identity_verified'],
            'personal_publishing_ready': aidni['personal_publishing_ready'],
            'organization_publishing_ready': False,
            'missing_permission': None if 'w_member_social' in aidni['scopes'] else 'w_member_social',
            'approval_pending': False,
            'token_expired': aidni['is_token_expired'],
            'publishing_disabled': not personal_flag_enabled,
            'status_label': (
                'Token Expired / Reauthorization Required' if aidni['reauth_required']
                else ('Missing Permission' if 'w_member_social' not in aidni['scopes'] or not aidni['member_identity_verified']
                      else ('Personal Publishing Ready' if personal_flag_enabled else 'Publishing Disabled'))
            ),
        },
        {
            'key': 'organization:145240694',
            'destination_type': 'organization',
            'app_key': APP_AIDNI_GLOBAL,
            'organization_id': aidni['org_id'],
            'author_urn': aidni['org_urn'],
            'label': 'Aidni Global LLP Company Page (Org 145240694)',
            'connected': aidni['authenticated'],
            'read_identity_verified': aidni['member_identity_verified'],
            'personal_publishing_ready': False,
            'organization_publishing_ready': aidni['company_publishing_ready'],
            'missing_permission': None if aidni['company_publishing_authorized'] else 'w_organization_social',
            'approval_pending': not aidni['company_publishing_authorized'],
            'token_expired': aidni['is_token_expired'],
            'publishing_disabled': not company_flag_enabled,
            'status_label': (
                'Token Expired / Reauthorization Required' if aidni['reauth_required']
                else ('Approval Pending' if not aidni['company_publishing_authorized']
                      else ('Organization Publishing Ready' if company_flag_enabled else 'Publishing Disabled'))
            ),
        },
        {
            'key': 'organization:145250613',
            'destination_type': 'organization',
            'app_key': APP_GAATHA_VENTURES,
            'organization_id': gaatha['org_id'],
            'author_urn': gaatha['org_urn'],
            'label': 'Gaatha Ventures Sh.p.k. Company Page (Org 145250613)',
            'connected': gaatha['authenticated'],
            'read_identity_verified': gaatha['member_identity_verified'],
            'personal_publishing_ready': False,
            'organization_publishing_ready': gaatha['company_publishing_ready'],
            'missing_permission': None if gaatha['company_publishing_authorized'] else 'w_organization_social',
            'approval_pending': not gaatha['company_publishing_authorized'],
            'token_expired': gaatha['is_token_expired'],
            'publishing_disabled': not company_flag_enabled,
            'status_label': (
                'Token Expired / Reauthorization Required' if gaatha['reauth_required']
                else ('Approval Pending' if not gaatha['company_publishing_authorized']
                      else ('Organization Publishing Ready' if company_flag_enabled else 'Publishing Disabled'))
            ),
        },
    ]

    return {
        'apps': apps_status,
        'destinations': destinations,
        'api_version': api_ver,
        'publishing_enabled': config.is_platform_publishing_enabled('linkedin'),
        'personal_publishing_enabled': personal_flag_enabled,
        'company_publishing_enabled': company_flag_enabled,
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

def _extract_restli_post_urn(resp, fallback_prefix: str) -> str:
    post_urn = resp.headers.get('x-restli-id') or resp.headers.get('X-RestLi-Id')
    if not post_urn:
        try:
            data = resp.json()
            post_urn = data.get('id') or data.get('urn')
        except Exception:
            post_urn = None
    return post_urn or f"urn:li:share:{fallback_prefix}_{int(time.time())}"


def create_personal_post(text: str,
                         app_key: Optional[str] = APP_AIDNI_GLOBAL,
                         access_token: Optional[str] = None,
                         image_urn: Optional[str] = None,
                         author_urn: Optional[str] = None) -> Dict[str, Any]:
    """
    Creates a personal LinkedIn profile post via POST https://api.linkedin.com/rest/posts
    using the verified member author URN (urn:li:person:<sub>) and w_member_social permission.
    Never guesses author IDs and strictly enforces personal publishing controls.
    """
    if not text or not str(text).strip():
        raise ValueError("Post text cannot be empty.")

    resolved_app = normalize_app_key(app_key or APP_AIDNI_GLOBAL)

    if not config.is_linkedin_personal_publishing_enabled():
        logger.info(f"🛡️ [SAFETY] LinkedIn personal publishing simulated/blocked (personal flag disabled, App: {resolved_app})")
        sim_id = f"urn:li:share:sim_personal_{int(time.time() * 1000)}"
        return {
            'id': sim_id,
            'share_urn': sim_id,
            'destination': 'personal',
            'app_key': resolved_app,
            'simulated': True,
            'success': True,
            'image_urn': image_urn,
            'message': 'Simulated publishing: POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED is 0'
        }

    token = access_token or get_active_token(resolved_app)
    if not token:
        return {
            'success': False,
            'destination': 'personal',
            'app_key': resolved_app,
            'error_code': 'UNAUTHENTICATED',
            'reauth_required': True,
            'error': f"Missing or expired LinkedIn access token for '{resolved_app}'. Re-authorization required."
        }

    resolved_author = (author_urn or '').strip()
    if not resolved_author:
        ident = resolve_member_author(resolved_app, access_token=token, verify_live=True)
        if not ident.get('success'):
            return {
                'success': False,
                'destination': 'personal',
                'app_key': resolved_app,
                'error_code': ident.get('error_code', 'IDENTITY_REQUIRED'),
                'error': ident.get('error') or 'Cannot verify personal LinkedIn author URN.'
            }
        resolved_author = ident['author_urn']

    if not resolved_author.startswith('urn:li:person:'):
        return {'success': False, 'destination': 'personal', 'error': f"Invalid personal author URN: '{resolved_author}'."}

    api_ver = get_rest_api_version()
    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": api_ver,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    payload: Dict[str, Any] = {
        "author": resolved_author,
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
        payload["content"] = {"media": {"id": image_urn}}

    try:
        resp = requests.post(REST_POSTS_URL, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code in (200, 201):
            post_urn = _extract_restli_post_urn(resp, resolved_app)
            logger.info(f"Successfully published personal LinkedIn post {post_urn} via '{resolved_app}'")
            return {
                'success': True,
                'id': post_urn,
                'share_urn': post_urn,
                'destination': 'personal',
                'author_urn': resolved_author,
                'app_key': resolved_app,
                'api_version': api_ver,
            }
        err = sanitize_log_message(resp.text)
        err_code = 'TOKEN_EXPIRED' if resp.status_code == 401 else (
            'PERMISSION_DENIED' if resp.status_code == 403 else (
                'API_VERSION_UNSUPPORTED' if resp.status_code == 426 else 'API_ERROR'
            )
        )
        logger.error(f"LinkedIn personal post rejected (HTTP {resp.status_code}, {err_code}): {err}")
        return {'success': False, 'status_code': resp.status_code, 'error_code': err_code, 'destination': 'personal', 'error': err}
    except Exception as e:
        safe_e = sanitize_log_message(str(e))
        logger.error(f"Exception publishing personal LinkedIn post via {resolved_app}: {safe_e}")
        return {'success': False, 'destination': 'personal', 'error_code': 'NETWORK_ERROR', 'error': safe_e}


def create_organization_post(organization_id: str,
                             text: str,
                             app_key: Optional[str] = None,
                             access_token: Optional[str] = None,
                             image_urn: Optional[str] = None) -> Dict[str, Any]:
    """
    Creates a post on LinkedIn for an organization using the modern REST Posts API.
    Endpoint: POST https://api.linkedin.com/rest/posts
    """
    if not organization_id or not str(organization_id).strip():
        raise ValueError("Organization ID is required to create a LinkedIn organization post.")
    if not text or not str(text).strip():
        raise ValueError("Post text cannot be empty.")

    clean_org_id = str(organization_id).replace("urn:li:organization:", "").strip()

    resolved_app = normalize_app_key(app_key) if app_key else None
    if not resolved_app:
        if clean_org_id == DEFAULT_ORG_ID_AIDNI_GLOBAL:
            resolved_app = APP_AIDNI_GLOBAL
        else:
            resolved_app = APP_GAATHA_VENTURES

    # Publishing Safety Guardrail (Organization publishing uses company guardrail flag)
    if not config.is_linkedin_company_publishing_enabled():
        logger.info(
            f"🛡️ [SAFETY] LinkedIn organization publishing blocked/simulated (POSTPILOT_PUBLISHING_ENABLED=0): "
            f"Organization ID {clean_org_id} (App: {resolved_app})"
        )
        sim_id = f"urn:li:share:sim_{int(time.time() * 1000)}"
        return {
            'id': sim_id,
            'share_urn': sim_id,
            'destination': 'organization',
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
        return {'success': False, 'destination': 'organization', 'error_code': 'UNAUTHENTICATED', 'error': f"Missing LinkedIn access token for application '{resolved_app}'."}

    api_ver = get_rest_api_version()
    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": api_ver,
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
        payload["content"] = {"media": {"id": image_urn}}

    try:
        resp = requests.post(REST_POSTS_URL, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code in (200, 201):
            post_urn = _extract_restli_post_urn(resp, clean_org_id)
            logger.info(f"Successfully published LinkedIn post {post_urn} for organization {clean_org_id}")
            return {
                'success': True,
                'id': post_urn,
                'share_urn': post_urn,
                'destination': 'organization',
                'organization_id': clean_org_id,
                'app_key': resolved_app,
                'api_version': api_ver,
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
                'error_code': 'CM_API_REQUIRED',
                'destination': 'organization',
                'error': (
                    "Organization publishing unauthorized (HTTP 403). "
                    "Community Management API (w_organization_social) access is required to publish to company pages."
                ),
                'details': err
            }
        else:
            err = sanitize_log_message(resp.text)
            logger.error(f"LinkedIn REST Posts API rejected (HTTP {resp.status_code}): {err}")
            return {'success': False, 'status_code': resp.status_code, 'destination': 'organization', 'error': err}
    except Exception as e:
        safe_e = sanitize_log_message(str(e))
        logger.error(f"Exception publishing to LinkedIn organization {clean_org_id}: {safe_e}")
        return {'success': False, 'destination': 'organization', 'error': safe_e}


# ==============================================================================
# LinkedIn REST Media Upload Procedures (Phase 2)
# ==============================================================================

def initialize_image_upload(owner_or_org_id: str,
                            app_key: Optional[str] = None,
                            access_token: Optional[str] = None,
                            is_personal: Optional[bool] = None) -> Dict[str, Any]:
    """
    Step 1: Initializes an image upload request on LinkedIn modern REST API.
    Supports either personal author URN (urn:li:person:...) or organization URN/ID.
    POST https://api.linkedin.com/rest/images?action=initializeUpload
    """
    raw_owner = str(owner_or_org_id or '').strip()
    if raw_owner.startswith('urn:li:person:'):
        owner_urn = raw_owner
        personal_mode = True if is_personal is None else is_personal
    else:
        clean_org_id = raw_owner.replace("urn:li:organization:", "").strip()
        owner_urn = f"urn:li:organization:{clean_org_id}"
        personal_mode = False if is_personal is None else is_personal

    resolved_app = normalize_app_key(app_key) if app_key else (APP_AIDNI_GLOBAL if personal_mode else APP_GAATHA_VENTURES)
    enabled = config.is_linkedin_personal_publishing_enabled() if personal_mode else config.is_linkedin_company_publishing_enabled()

    if not enabled:
        return {
            'success': True,
            'upload_url': f"https://api.linkedin.com/mediaUpload/simulated_{int(time.time())}",
            'image_urn': f"urn:li:image:sim_{int(time.time() * 1000)}",
            'owner_urn': owner_urn,
            'simulated': True
        }

    token = access_token or get_active_token(resolved_app)
    if not token:
        return {'success': False, 'error': f"Missing access token for {resolved_app}."}

    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": get_rest_api_version(),
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    payload = {
        "initializeUploadRequest": {
            "owner": owner_urn
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
                'owner_urn': owner_urn,
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
    if 'simulated' in str(upload_url or ''):
        return True

    if not os.path.isfile(file_path):
        return False

    try:
        with open(file_path, 'rb') as f:
            data = f.read()

        headers = {"Content-Type": "application/octet-stream"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        resp = requests.put(upload_url, data=data, headers=headers, timeout=DEFAULT_TIMEOUT)
        return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Error uploading image binary to LinkedIn: {sanitize_log_message(str(e))}")
        return False
