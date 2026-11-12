import os
import re
import requests
import time
import json
import logging
import config

logger = logging.getLogger(__name__)

# Configuration for API requests
MAX_RETRIES = 5
INITIAL_BACKOFF = 2  # seconds
FB_API_VERSION = "v19.0"
BASE_URL = f"https://graph.facebook.com/{FB_API_VERSION}"

DEFAULT_TIMEOUT = 30  # seconds

def mask_token_preview(token):
    """Safely masks a token for diagnostic logging."""
    if not token:
        return "[NONE]"
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"

# Precompiled regex patterns for comprehensive credential sanitization
_RE_AUTH_HEADER = re.compile(
    r'(?i)(authorization:\s*(?:bearer|oauth|basic)?\s*)[^\s\'",\)]+'
)
_RE_AUTH_DICT = re.compile(
    r'(?i)(["\']authorization["\']\s*:\s*["\'](?:bearer|oauth|basic)?\s*)[^"\']+(["\'])'
)
_RE_QUERY_CREDENTIALS = re.compile(
    r'(?i)(\b(?:[a-zA-Z0-9_]*(?:token|secret|password|api_key)|access(?:_|%5f)token|input(?:_|%5f)token|appsecret(?:_|%5f)proof)=)'
    r'([^\s&\'"\)>]+)'
)
_RE_DICT_CREDENTIALS = re.compile(
    r'(?i)(["\'](?:[a-zA-Z0-9_]*(?:token|secret|password|api_key)|access_token|input_token|appsecret_proof)["\']\s*:\s*["\'])'
    r'[^"\']+'
    r'(["\'])'
)
_RE_EAA_TOKEN = re.compile(r'\bEAA[a-zA-Z0-9_\-]{15,}\b')
_RE_APP_TOKEN = re.compile(r'\b\d{14,18}\|[a-zA-Z0-9_\-]{20,}\b')
_RE_IG_TOKEN = re.compile(r'\bIG(?:QV)?[a-zA-Z0-9_\-]{20,}\b')
_RE_BEARER_TOKEN = re.compile(r'(?i)\b(?:bearer|oauth)\s+([a-zA-Z0-9_\-\.\|]{15,})\b')

def sanitize_log_message(msg):
    """
    Sanitizes sensitive tokens, credential query parameters, Authorization headers,
    and secret structures from log messages, CLI output, and exception traces
    to prevent accidental credential exposure.
    """
    if not msg:
        return ""
    if not isinstance(msg, str):
        msg = str(msg)

    # 1. Redact Authorization headers (plain headers and dict-like representations)
    sanitized = _RE_AUTH_HEADER.sub(r'\1[REDACTED]', msg)
    sanitized = _RE_AUTH_DICT.sub(r'\1[REDACTED]\2', sanitized)

    # 2. Redact URL query parameters (standard and URL-encoded keys)
    sanitized = _RE_QUERY_CREDENTIALS.sub(r'\1[REDACTED]', sanitized)

    # 3. Redact key-value pairs in JSON / dictionary-like text
    sanitized = _RE_DICT_CREDENTIALS.sub(r'\1[REDACTED]\2', sanitized)

    # 4. Redact Meta and generic token patterns
    sanitized = _RE_EAA_TOKEN.sub('[REDACTED_TOKEN]', sanitized)
    sanitized = _RE_APP_TOKEN.sub('[REDACTED_APP_TOKEN]', sanitized)
    sanitized = _RE_IG_TOKEN.sub('[REDACTED_TOKEN]', sanitized)
    sanitized = _RE_BEARER_TOKEN.sub(r'Bearer [REDACTED]', sanitized)

    # 5. Redact any known configured environment token values
    try:
        for key, val in os.environ.items():
            if any(term in key for term in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY')):
                if val and len(val) >= 8 and not val.isdigit() and val not in ('True', 'False', 'None'):
                    sanitized = sanitized.replace(val, '[REDACTED_SECRET]')
    except Exception:
        pass

    return sanitized

def classify_facebook_error(response_json, status_code=200):
    """
    Classifies Facebook API errors into distinct categories:
    - RATE_LIMIT: Transient rate limit (codes 4, 17, 32, 613, HTTP 429)
    - AUTH_ERROR: Permanent token invalidation, expiration, or revocation (codes 102, 190, 463, 467)
    - PERMISSION_ERROR: Missing required Page permissions (codes 10, 200, 283)
    - DUPLICATE_POST: Identical post content rejected by Meta (code 506)
    - CLIENT_ERROR: Invalid parameter, blocked policy, or payload error (codes 100, 368)
    - SERVER_ERROR: Transient Meta server errors (codes 1, 2, HTTP 500, 502, 503, 504)
    - NETWORK_ERROR: Connection or timeout failures
    """
    if status_code in (500, 502, 503, 504):
        return 'SERVER_ERROR'
    if status_code == 429:
        return 'RATE_LIMIT'

    if isinstance(response_json, dict) and 'error' in response_json:
        err = response_json['error']
        code = err.get('code') if isinstance(err, dict) else None
        if code in (4, 17, 32, 613):
            return 'RATE_LIMIT'
        if code in (102, 190, 463, 467):
            return 'AUTH_ERROR'
        if code in (10, 200, 283):
            return 'PERMISSION_ERROR'
        if code == 506:
            return 'DUPLICATE_POST'
        if code in (1, 2):
            return 'SERVER_ERROR'
        if code in (100, 368):
            return 'CLIENT_ERROR'
    return 'UNKNOWN_ERROR'

def get_access_token(channel_key=None):
    """
    Retrieves Facebook access token.
    Priority:
    1. Channel-specific environment variable (if channel_key provided)
    2. FB_ACCESS_TOKEN or FB_TOKEN environment variable
    3. .env file fallback
    """
    if channel_key:
        ck = channel_key.upper()
        for k in (f'FB_ACCESS_TOKEN_{ck}', f'FB_PAGE_TOKEN_{ck}', f'FB_TOKEN_{ck}'):
            val = os.getenv(k)
            if val and val.strip():
                return val.strip()

    token = os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN')
    if token:
        return token.strip()

    # Try to read from .env file (manual parsing for robustness)
    if os.path.exists('.env'):
        try:
            with open('.env', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        if k.strip() in ('FB_ACCESS_TOKEN', 'FB_TOKEN'):
                            return v.strip().strip('"\'')
        except Exception as e:
            logger.warning(f"Failed to read token from .env: {sanitize_log_message(str(e))}")

    return None

def get_page_token(user_token=None, page_id=None, channel_key=None):
    """
    Resolves a Page Access Token for a specific page.
    Priority:
    1. Direct channel/page token override in environment:
       - FB_PAGE_TOKEN_{page_id}
       - FB_PAGE_TOKEN_{channel_key} / FB_ACCESS_TOKEN_{channel_key}
       - Known alias page tokens (FB_PAGE_TOKEN_TOUR, FB_PAGE_TOKEN_SUITE, etc.)
       - FB_PAGE_ACCESS_TOKEN
    2. Check if user_token is ALREADY a Page Access Token for this page (GET /me?fields=id,name)
    3. Exchange User Access Token for Page Access Token via GET /me/accounts
    4. Direct Page token lookup via GET /{page_id}?fields=id,name,access_token
    """
    if not page_id:
        logger.error("No page_id provided to get_page_token.")
        return None

    page_id_str = str(page_id).strip()

    # Step 1: Check environment overrides
    env_keys_to_check = [f'FB_PAGE_TOKEN_{page_id_str}']
    if channel_key:
        ck = channel_key.upper()
        env_keys_to_check.extend([f'FB_PAGE_TOKEN_{ck}', f'FB_ACCESS_TOKEN_{ck}', f'FB_TOKEN_{ck}'])

    # Map known page IDs to alias keys
    known_aliases = {
        '967550829768297': ['FB_PAGE_TOKEN_TOUR', 'FB_PAGE_TOKEN_SUITE', 'FB_PAGE_TOKEN_NEXORA_SUITE', 'FB_ACCESS_TOKEN_TOUR', 'FB_ACCESS_TOKEN_SUITE'],
        '954901604381882': ['FB_PAGE_TOKEN_NZ', 'FB_PAGE_TOKEN_PHOENIX', 'FB_PAGE_TOKEN_NEXORA_BY_PHOENIX', 'FB_ACCESS_TOKEN_NZ', 'FB_ACCESS_TOKEN_PHOENIX'],
        '1028368893692590': ['FB_PAGE_TOKEN_GAATHA', 'FB_PAGE_TOKEN_GAATHA_AI', 'FB_ACCESS_TOKEN_GAATHA', 'FB_ACCESS_TOKEN_GAATHA_AI'],
    }
    if page_id_str in known_aliases:
        env_keys_to_check.extend(known_aliases[page_id_str])

    env_keys_to_check.append('FB_PAGE_ACCESS_TOKEN')

    for k in env_keys_to_check:
        override = os.getenv(k)
        if override and override.strip():
            logger.info(f"Using direct page token override from {k} for page {page_id_str}")
            return override.strip()

    if not user_token:
        user_token = get_access_token(channel_key=channel_key)

    if not user_token:
        logger.error(f"No user or page token available for page {page_id_str}.")
        return None

    # Step 2: Check if user_token is ALREADY a Page Access Token for this page
    try:
        me_resp = requests.get(
            f"{BASE_URL}/me",
            params={"access_token": user_token, "fields": "id,name"},
            timeout=DEFAULT_TIMEOUT
        ).json()
        if str(me_resp.get('id')) == page_id_str:
            logger.info(f"Verified token is already a Page Access Token for '{me_resp.get('name')}' (ID: {page_id_str})")
            return user_token
    except Exception as e:
        logger.debug(f"Could not verify token via /me: {sanitize_log_message(str(e))}")

    # Step 3: Exchange User Access Token for Page Access Token via /me/accounts
    try:
        url = f"{BASE_URL}/me/accounts"
        params = {"access_token": user_token, "limit": 100}
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        res_json = resp.json()
        if 'data' in res_json:
            for page in res_json['data']:
                if str(page.get('id')) == page_id_str:
                    logger.info(f"Successfully resolved Page Access Token for page '{page.get('name')}' (ID: {page_id_str})")
                    return page.get('access_token')

        # Step 4: Fallback direct lookup via /{page_id}?fields=id,name,access_token
        try:
            page_resp = requests.get(
                f"{BASE_URL}/{page_id_str}",
                params={"access_token": user_token, "fields": "id,name,access_token"},
                timeout=DEFAULT_TIMEOUT
            ).json()
            if page_resp.get('access_token'):
                logger.info(f"Resolved Page Access Token directly from /{page_id_str}")
                return page_resp.get('access_token')
        except Exception:
            pass

        if 'error' in res_json:
            err_msg = res_json['error'].get('message', 'Unknown')
            err_code = res_json['error'].get('code')
            logger.error(f"Graph API Error in get_page_token for page {page_id_str}: {sanitize_log_message(err_msg)} (code={err_code})")
        else:
            logger.error(f"Page ID {page_id_str} was not found among user's managed Facebook accounts.")
        return None
    except Exception as e:
        logger.error(f"Exception in get_page_token for page {page_id_str}: {sanitize_log_message(str(e))}")
        return None

def audit_publishing_capabilities(token, page_id=None):
    """
    Audits token validity, expiration, and granted publishing permissions without exposing credentials.
    Returns structured audit results.
    """
    if not token:
        return {'valid': False, 'reason': 'Missing token'}

    debug_data = get_token_info(token)
    if not debug_data:
        return {'valid': False, 'reason': 'Could not query Meta debug_token endpoint'}

    is_valid = bool(debug_data.get('is_valid', False))
    scopes = set(debug_data.get('scopes', []))
    expires_at = debug_data.get('expires_at', 0)
    profile_id = str(debug_data.get('profile_id', ''))
    token_type = debug_data.get('type', 'USER')

    can_manage_posts = 'pages_manage_posts' in scopes
    can_read_engagement = 'pages_read_engagement' in scopes
    can_publish_video = 'publish_video' in scopes
    can_publish_instagram = 'instagram_content_publish' in scopes
    can_show_pages = 'pages_show_list' in scopes

    matches_page = bool(page_id and profile_id == str(page_id))

    return {
        'valid': is_valid,
        'token_type': token_type,
        'expires_never': expires_at == 0,
        'expires_at': expires_at,
        'profile_id': profile_id,
        'matches_page': matches_page,
        'scopes_count': len(scopes),
        'can_publish_facebook': is_valid and can_manage_posts,
        'can_publish_video': is_valid and can_publish_video,
        'can_publish_instagram': is_valid and can_publish_instagram,
        'can_read_engagement': can_read_engagement,
        'can_show_pages': can_show_pages,
        'missing_permissions': [
            perm for perm in ['pages_manage_posts', 'pages_read_engagement', 'pages_show_list']
            if perm not in scopes
        ]
    }

def get_token_info(token):
    """
    Debug helper to check token validity, scopes, and expiration.
    Essential for determining if a token needs manual re-authentication.
    """
    if not token:
        return None
    url = f"{BASE_URL}/debug_token"
    params = {
        "input_token": token,
        "access_token": token
    }
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        res_json = resp.json()
        if 'data' in res_json:
            data = res_json['data']
            status = "VALID" if data.get('is_valid') else "INVALID"
            expires = data.get('data_access_expires_at', 'Never')
            logger.info(f"Token Check [{status}]: Expires: {expires}, Scopes: {data.get('scopes')}")
            return data
        return None
    except Exception as e:
        logger.error(f"Failed to debug token: {sanitize_log_message(str(e))}")
        return None

def _is_rate_limited(response_json, status_code):
    """Check if the response indicates a rate limit error."""
    if status_code == 429:
        return True
    if isinstance(response_json, dict) and 'error' in response_json:
        # FB Error codes for rate limiting: 4, 17, 32, 613
        code = response_json['error'].get('code') if isinstance(response_json['error'], dict) else None
        if code in (4, 17, 32, 613):
            return True
    return False

def _request_with_retry(method, url, **kwargs):
    """
    Helper to perform requests with exponential backoff on transient errors.
    Bails out immediately on permanent auth/permission errors without wasteful retries.
    """
    # Publishing Safety Guardrail: Intercept mutating publish calls when disabled
    if method.upper() in ('POST', 'PUT', 'DELETE'):
        is_wa_endpoint = '/messages' in url
        is_ig_endpoint = any(ep in url for ep in ('/media', '/media_publish'))
        is_fb_endpoint = any(ep in url for ep in ('/feed', '/photos', '/videos'))
        if is_wa_endpoint or is_ig_endpoint or is_fb_endpoint:
            target_plat = 'whatsapp' if is_wa_endpoint else ('instagram' if is_ig_endpoint else 'facebook')
            if not config.is_platform_publishing_enabled(target_plat):
                logger.info(f"🛡️ [SAFETY] External Meta publishing intercepted (POSTPILOT_PUBLISHING_ENABLED=0): {method} {url}")
                simulated_id = f"simulated_meta_{int(time.time() * 1000)}"
                return {
                    'id': simulated_id,
                    'post_id': simulated_id,
                    'simulated': True,
                    'success': True,
                    'message': 'Simulated publishing: POSTPILOT_PUBLISHING_ENABLED is 0'
                }

    backoff = INITIAL_BACKOFF
    kwargs.setdefault('timeout', DEFAULT_TIMEOUT)

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, **kwargs)
            try:
                res_json = resp.json()
            except Exception:
                res_json = {'error': {'message': sanitize_log_message(resp.text), 'code': resp.status_code}}

            # Classify response
            err_category = classify_facebook_error(res_json, resp.status_code)

            # Permanent errors: do not retry
            if err_category in ('AUTH_ERROR', 'PERMISSION_ERROR', 'CLIENT_ERROR', 'DUPLICATE_POST'):
                err_msg = res_json['error'].get('message', 'Client Error') if isinstance(res_json.get('error'), dict) else str(res_json.get('error'))
                logger.error(f"❌ Permanent Facebook API error ({err_category}): {sanitize_log_message(err_msg)}")
                return res_json

            # Rate limits or transient server errors: retry with backoff
            if err_category in ('RATE_LIMIT', 'SERVER_ERROR'):
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"⚠️ {err_category} hit (attempt {attempt+1}/{MAX_RETRIES}). "
                        f"Backing off for {backoff}s..."
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    if 'files' in kwargs:  # Reset file pointer for retries
                        for file_key, file_val in kwargs['files'].items():
                            if hasattr(file_val[1], 'seek'):
                                file_val[1].seek(0)
                    continue

            return res_json
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            safe_err = sanitize_log_message(str(e))
            logger.warning(f"⚠️ Network error (attempt {attempt+1}/{MAX_RETRIES}): {safe_err}")
            if attempt == MAX_RETRIES - 1:
                return {'error': {'message': f"Network error after {MAX_RETRIES} attempts: {safe_err}", 'category': 'NETWORK_ERROR'}}
            time.sleep(backoff)
            backoff *= 2
        except Exception as e:
            safe_err = sanitize_log_message(str(e))
            logger.error(f"❌ Unexpected request exception: {safe_err}")
            if attempt == MAX_RETRIES - 1:
                return {'error': {'message': safe_err, 'category': 'UNKNOWN_ERROR'}}
            time.sleep(backoff)
            backoff *= 2

    return {'error': {'message': 'Max retries exceeded', 'category': 'RATE_LIMIT'}}

KNOWN_PAGE_ENV_ALIASES = {
    '967550829768297': 'SUITE',
    '954901604381882': 'PHOENIX',
    '1028368893692590': 'GAATHA_AI',
    '178168346255851': 'GAATHA',
    '374211199112915': 'GRAHAK_CHETNA',
}

def get_canonical_page_slug(page_id, page_name=''):
    """Returns a stable uppercase env-var suffix for a Meta Page ID/name."""
    pid = str(page_id or '').strip()
    if pid in KNOWN_PAGE_ENV_ALIASES:
        return KNOWN_PAGE_ENV_ALIASES[pid]
    slug = re.sub(r'[^A-Z0-9]+', '_', str(page_name or '').strip().upper()).strip('_')
    return slug or f"PAGE_{pid}"

def safely_update_env_vars(updates, env_path=None):
    """
    Atomically updates non-secret Page/IG ID keys in .env and os.environ
    without altering existing tokens, secrets, comments, or safety flags.
    """
    import tempfile
    from pathlib import Path

    if not updates:
        return False

    target_path = Path(env_path) if env_path else Path(os.getenv('POSTPILOT_ENV_FILE') or (Path(__file__).resolve().parent / '.env'))
    lines = []
    if target_path.exists():
        lines = target_path.read_text(encoding='utf-8').splitlines(keepends=True)

    new_lines = []
    pending = {str(k): str(v) for k, v in updates.items()}
    changed = False
    for line in lines:
        stripped = line.strip()
        if '=' in stripped and not stripped.startswith('#'):
            key, existing_val = stripped.split('=', 1)
            key = key.strip()
            if key in pending:
                val = pending.pop(key)
                if existing_val != val:
                    changed = True
                new_lines.append(f"{key}={val}\n")
                continue
        new_lines.append(line)

    if pending:
        changed = True
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        for key, val in pending.items():
            new_lines.append(f"{key}={val}\n")

    if changed or not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix='.env_sync_', dir=str(target_path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as tf:
                tf.writelines(new_lines)
            if os.name == 'posix':
                os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, str(target_path))
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    for key, val in updates.items():
        os.environ[str(key)] = str(val)
    return changed

def sync_connected_pages_to_env(env_path=None, timeout=15):
    """
    Discovers all Facebook Pages (and linked Instagram accounts) connected through
    the active FB_ACCESS_TOKEN and maps their non-secret IDs into .env & os.environ.
    """
    token = get_access_token()
    if not token:
        return {'success': False, 'skipped': True, 'reason': 'No FB_ACCESS_TOKEN configured'}

    next_url = f"{BASE_URL}/me/accounts"
    params = {
        'access_token': token,
        'fields': 'id,name,instagram_business_account{id,username,name},whatsapp_number',
        'limit': 100
    }
    all_pages = []
    while next_url:
        resp = requests.get(next_url, params=params, timeout=timeout)
        data = resp.json()
        if resp.status_code != 200 or 'error' in data:
            err = data.get('error', {}).get('message', resp.text) if isinstance(data, dict) else resp.text
            return {'success': False, 'error': sanitize_log_message(str(err))}
        all_pages.extend(data.get('data', []))
        next_url = (data.get('paging') or {}).get('next')
        params = None

    if not all_pages:
        return {'success': True, 'pages_count': 0, 'pages': [], 'updated': False}

    updates = {}
    page_ids = []
    pages_summary = []
    for page in all_pages:
        pid = str(page.get('id') or '').strip()
        pname = str(page.get('name') or '').strip()
        if not pid:
            continue
        slug = get_canonical_page_slug(pid, pname)
        updates[f"FB_PAGE_ID_{slug}"] = pid
        if pid not in page_ids:
            page_ids.append(pid)
        ig = page.get('instagram_business_account')
        ig_id = str(ig.get('id') or '').strip() if isinstance(ig, dict) else ''
        if ig_id:
            updates[f"INSTA_ID_{slug}"] = ig_id
        pages_summary.append({
            'id': pid,
            'name': pname,
            'slug': slug,
            'instagram_id': ig_id or None,
            'whatsapp_number': page.get('whatsapp_number')
        })

    updates['FB_CONNECTED_PAGE_IDS'] = ','.join(page_ids)
    changed = safely_update_env_vars(updates, env_path=env_path)
    return {
        'success': True,
        'pages_count': len(pages_summary),
        'updated': changed,
        'env_keys': sorted(updates.keys()),
        'pages': pages_summary,
    }

