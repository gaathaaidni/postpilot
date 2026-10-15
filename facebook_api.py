import os
import requests
import time
import json
import logging

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

def classify_facebook_error(response_json, status_code=200):
    """
    Classifies Facebook API errors into distinct categories:
    - RATE_LIMIT: Transient rate limit (codes 4, 17, 32, 613, HTTP 429)
    - AUTH_ERROR: Permanent token invalidation, expiration, or revocation (code 190)
    - PERMISSION_ERROR: Missing required Page permissions (codes 10, 200)
    - CLIENT_ERROR: Invalid parameter or payload (code 100)
    - SERVER_ERROR: Transient Meta server errors (HTTP 500, 502, 503, 504)
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
        if code == 190:
            return 'AUTH_ERROR'
        if code in (10, 200):
            return 'PERMISSION_ERROR'
        if code == 100:
            return 'CLIENT_ERROR'
    return 'UNKNOWN_ERROR'

def get_access_token():
    """
    Retrieves the Facebook user access token.
    Priority: Environment Variable (FB_ACCESS_TOKEN or FB_TOKEN) > .env file.
    """
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
            logger.warning(f"Failed to read token from .env: {e}")

    return None

def get_page_token(user_token, page_id):
    """
    Exchanges a User Access Token for a Page Access Token for a specific page.
    This ensures API calls are made on behalf of the page.
    Supports channel-specific page token overrides and direct page tokens.
    """
    if not page_id:
        logger.error("No page_id provided to get_page_token.")
        return None

    # Check for direct channel/page token override in environment
    page_token_override = (
        os.getenv(f'FB_PAGE_TOKEN_{page_id}') or
        os.getenv('FB_PAGE_ACCESS_TOKEN')
    )
    if page_token_override and page_token_override.strip():
        return page_token_override.strip()

    if not user_token:
        logger.error("No user token provided to get_page_token.")
        return None

    try:
        url = f"{BASE_URL}/me/accounts"
        params = {"access_token": user_token, "limit": 100}
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        res_json = resp.json()
        if 'data' in res_json:
            for page in res_json['data']:
                if str(page.get('id')) == str(page_id):
                    return page.get('access_token')

        # If user_token is already a Page Access Token for this page, /me/accounts may fail or be empty.
        # Verify if /me corresponds directly to this page_id.
        try:
            me_resp = requests.get(f"{BASE_URL}/me", params={"access_token": user_token, "fields": "id"}, timeout=DEFAULT_TIMEOUT).json()
            if str(me_resp.get('id')) == str(page_id):
                return user_token
        except Exception:
            pass

        if 'error' in res_json:
            err_msg = res_json['error'].get('message', 'Unknown')
            err_code = res_json['error'].get('code')
            logger.error(f"Graph API Error in get_page_token for page {page_id}: {err_msg} (code={err_code})")
        return None
    except Exception as e:
        logger.error(f"Exception in get_page_token for page {page_id}: {e}")
        return None

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
        logger.error(f"Failed to debug token: {e}")
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
    backoff = INITIAL_BACKOFF
    kwargs.setdefault('timeout', DEFAULT_TIMEOUT)

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, **kwargs)
            try:
                res_json = resp.json()
            except Exception:
                res_json = {'error': {'message': resp.text, 'code': resp.status_code}}

            # Classify response
            err_category = classify_facebook_error(res_json, resp.status_code)

            # Permanent errors: do not retry
            if err_category in ('AUTH_ERROR', 'PERMISSION_ERROR', 'CLIENT_ERROR'):
                err_msg = res_json['error'].get('message', 'Client Error') if isinstance(res_json.get('error'), dict) else str(res_json.get('error'))
                logger.error(f"❌ Permanent Facebook API error ({err_category}): {err_msg}")
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
            logger.warning(f"⚠️ Network error (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                return {'error': {'message': f"Network error after {MAX_RETRIES} attempts: {e}", 'category': 'NETWORK_ERROR'}}
            time.sleep(backoff)
            backoff *= 2
        except Exception as e:
            logger.error(f"❌ Unexpected request exception: {e}")
            if attempt == MAX_RETRIES - 1:
                return {'error': {'message': str(e), 'category': 'UNKNOWN_ERROR'}}
            time.sleep(backoff)
            backoff *= 2

    return {'error': {'message': 'Max retries exceeded', 'category': 'RATE_LIMIT'}}