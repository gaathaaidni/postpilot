"""
Script to verify Facebook Access Token permissions and validity.
Run: python verify_token.py
"""
import os
import requests
import datetime
import json
import json # This path needs to be updated to APP_ROOT / 'config'

def load_token():
    # Priority: Env Var > .env > token.txt
    token = os.environ.get('FB_ACCESS_TOKEN') or os.environ.get('FB_TOKEN')
    if token:
        return token.strip()

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
        except Exception:
            pass

    if os.path.exists('token.txt'):
        try:
            with open('token.txt', 'r') as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def print_rate_limits(headers):
    """Parses and prints FB Rate Limit headers."""
    # App-level usage
    app_usage = headers.get('x-app-usage')
    if app_usage:
        try:
            usage = json.loads(app_usage)
            print(f"\n📈 App Rate Limit Usage:")
            print(f"   Call Count: {usage.get('call_count')}% | CPU: {usage.get('total_cputime')}% | Time: {usage.get('total_time')}%")
        except Exception:
            print(f"\n📈 App Rate Limit Usage: {app_usage}")

def main():
    token = load_token()
    if not token:
        print("❌ Error: No token found. Set FB_ACCESS_TOKEN in .env or token.txt")
        return

    print(f"🔍 Checking Token: {token[:10]}...{token[-5:]}")
    
    # Facebook Debug Token Endpoint
    # Using the token to check itself
    url = "https://graph.facebook.com/v19.0/debug_token"
    params = {
        'input_token': token,
        'access_token': token 
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'error' in data:
            print(f"❌ API Error: {data['error']['message']}")
            print("   (Note: The token might be invalid or expired)")
            return

        data = data.get('data', {})
        is_valid = data.get('is_valid')
        
        if is_valid:
            print(f"\n✅ Token is VALID")
            print(f"   App ID:  {data.get('app_id')}")
            print(f"   User ID: {data.get('user_id')}")
            
            expires_at = data.get('expires_at', 0)
            if expires_at == 0:
                print("   Expires: Never (System/Page token)")
            else:
                exp_dt = datetime.datetime.fromtimestamp(expires_at)
                print(f"   Expires: {exp_dt}")

            scopes = data.get('scopes', [])
            print(f"\n🔐 Permissions ({len(scopes)}):")
            for scope in sorted(scopes):
                print(f"   - {scope}")
            
            # Check for critical permissions
            needed = ['pages_show_list', 'pages_read_engagement', 'pages_manage_posts', 'instagram_basic', 'instagram_content_publish']
            missing = [p for p in needed if p not in scopes]
            
            if missing:
                print("\n⚠️  MISSING CRITICAL PERMISSIONS:")
                for m in missing:
                    print(f"   ❌ {m}")
            else:
                print("\n✨ All critical permissions present.")
                
        else:
            print(f"\n❌ Token is INVALID")
            if 'error' in data:
                print(f"   Reason: {data['error'].get('message')}")

        # Secondary check for Rate Limits by hitting a data endpoint
        me_url = "https://graph.facebook.com/v19.0/me"
        me_res = requests.get(me_url, params={'access_token': token})
        print_rate_limits(me_res.headers)

    except Exception as e:
        print(f"❌ Network Error: {e}")

if __name__ == "__main__":
    main()