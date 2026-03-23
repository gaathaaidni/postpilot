"""
Script to fetch full details of connected Facebook Pages, Instagram Accounts,
and WhatsApp Numbers using the configured Access Token.
"""
import os
import requests

def load_token():
    """Load token from env var, .env file, or token.txt"""
    # 1. Try Environment Variable
    token = os.environ.get('FB_ACCESS_TOKEN') or os.environ.get('FB_TOKEN')
    if token: return token.strip()
    
    # 2. Try .env file manually
    if os.path.exists('.env'):
        try:
            with open('.env', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        if k in ('FB_ACCESS_TOKEN', 'FB_TOKEN'):
                            return v.strip().strip('"').strip("'")
        except: pass

    # 3. Try token.txt
    if os.path.exists('token.txt'):
        try:
            with open('token.txt', 'r') as f:
                return f.read().strip()
        except: pass
        
    return None

def main():
    print("🚀 Fetching Social Media Connections...\n")
    
    token = load_token()
    if not token:
        print("❌ ERROR: Could not find Access Token.")
        print("   Please set FB_ACCESS_TOKEN in .env or create 'token.txt'")
        return

    session = requests.Session()
    params = {'access_token': token}
    
    # 1. Get User
    try:
        me = session.get("https://graph.facebook.com/v19.0/me", params=params).json()
        if 'error' in me:
            print(f"❌ API Error: {me['error']['message']}")
            return
        print(f"👤 User: {me.get('name')} (ID: {me.get('id')})")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return
    
    # 2. Get Accounts with fields
    # whatsapp_number requires permissions like 'pages_messaging' to appear if linked
    fields = "name,id,instagram_business_account{id,username,name},whatsapp_number"
    
    p_params = params.copy()
    p_params['fields'] = fields
    p_params['limit'] = 100
    
    print("\n📄 Scanning Pages...\n")
    
    try:
        resp = session.get("https://graph.facebook.com/v19.0/me/accounts", params=p_params)
        data = resp.json()
        if 'error' in data:
            print(f"❌ Error fetching pages: {data['error']['message']}")
            return
            
        pages = data.get('data', [])
    except Exception as e:
        print(f"❌ Network Error: {e}")
        return
    
    if not pages:
        print("   No pages found.")
        return

    for i, page in enumerate(pages, 1):
        print(f"[{i}] {page.get('name')}")
        print(f"    🆔 Page ID:   {page.get('id')}")
        
        # Instagram
        ig = page.get('instagram_business_account')
        if ig:
            print(f"    📸 Instagram: @{ig.get('username')} (ID: {ig.get('id')})")
        else:
            print(f"    📸 Instagram: Not connected")
            
        # WhatsApp
        wa = page.get('whatsapp_number')
        if wa:
            print(f"    💬 WhatsApp:  {wa}")
        else:
            print(f"    💬 WhatsApp:  Not linked (or hidden)")
            
        print("-" * 40)
    
    print("\n✅ Done.")

if __name__ == "__main__":
    main()
