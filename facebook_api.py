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

class FacebookAPIError(Exception):
    """Custom exception for Facebook Graph API errors."""
    pass

def get_access_token():
    """
    Retrieves the Facebook user access token.
    Priority: Environment Variable (FB_ACCESS_TOKEN or FB_TOKEN) > .env file > token.txt file.
    """
    token = os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN')
    if token:
        return token.strip()

    # Try to read from .env file (manual parsing for robustness)
    if os.path.exists('.env'):
        try:
            with open('.env', 'r') as f:
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

    # Fallback to token.txt
    if os.path.exists('token.txt'):
        try:
            with open('token.txt', 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.warning(f"Failed to read token from token.txt: {e}")
    return None

def get_page_token(user_token, page_id):
    """
    Exchanges a User Access Token for a Page Access Token for a specific page.
    This ensures API calls are made on behalf of the page.
    """
    if not user_token:
        logger.error("No user token provided to get_page_token.")
        return None
    try:
        url = f"{BASE_URL}/me/accounts"
        params = {"access_token": user_token}
        resp = requests.get(url, params=params).json()
        if 'data' in resp:
            for page in resp['data']:
                if page.get('id') == page_id:
                    return page.get('access_token')
        if 'error' in resp:
            logger.error(f"Graph API Error in get_page_token for page {page_id}: {resp['error'].get('message')}")
        return None
    except Exception as e:
        logger.error(f"Exception in get_page_token for page {page_id}: {e}")
        return None

def get_token_info(token):
    """
    Debug helper to check token validity, scopes, and expiration.
    Essential for determining if a token needs manual re-authentication.
    """
    url = f"{BASE_URL}/debug_token"
    params = {
        "input_token": token,
        "access_token": token
    }
    try:
        resp = requests.get(url, params=params)
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
    if 'error' in response_json:
        # FB Error codes for rate limiting: 4, 17, 32, 613
        code = response_json['error'].get('code')
        if code in (4, 17, 32, 613):
            return True
    return False

def _request_with_retry(method, url, **kwargs):
    """Helper to perform requests with exponential backoff on rate limits."""
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(method, url, **kwargs)
            res_json = resp.json()
            
            if _is_rate_limited(res_json, resp.status_code):
                logger.warning(f"⚠️ Rate limit hit (attempt {attempt+1}/{MAX_RETRIES}). Backing off for {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
                if 'files' in kwargs: # Reset file pointer for retries
                    for file_key, file_val in kwargs['files'].items():
                        if hasattr(file_val[1], 'seek'):
                            file_val[1].seek(0)
                continue
            
            return res_json
        except Exception as e:
            logger.error(f"❌ Request exception: {e}")
            if attempt == MAX_RETRIES - 1:
                return {'error': str(e)}
            time.sleep(backoff)
            backoff *= 2
    return {'error': 'Max retries exceeded'}