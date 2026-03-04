"""Utility to query Facebook Graph API using token from .env and print page/IG IDs.

Run:
    python fetch_fb_info.py

This will read FB_TOKEN from .env and list pages you manage along with their IDs,
plus try to retrieve connected Instagram business account IDs if available.
"""
import os
import requests

# simple .env loader
def load_env(path):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k,v = line.split("=",1)
                env[k.strip()] = v.strip()
    return env

env = load_env('.env')
FB_TOKEN = env.get('FB_TOKEN')
if not FB_TOKEN:
    print("FB_TOKEN not set in .env")
    exit(1)

base_url = "https://graph.facebook.com/v19.0"

print("Using token from .env.")

# get user info
user_resp = requests.get(f"{base_url}/me?access_token={FB_TOKEN}").json()
print("User:", user_resp)

# get pages managed by this user
pages_resp = requests.get(f"{base_url}/me/accounts?access_token={FB_TOKEN}").json()
print("Pages you manage:")
updates = {}
for p in pages_resp.get("data", []):
    name = p.get('name')
    page_id = p.get('id')
    print(f"  {name} (id={page_id})")
    # gather variable-friendly name
    var_base = name.upper().replace(' ', '_').replace('.', '_')
    updates[f"FB_PAGE_ID_{var_base}"] = page_id
    # try to fetch insta business account id if connected
    if page_id:
        ig_resp = requests.get(f"{base_url}/{page_id}?fields=instagram_business_account&access_token={FB_TOKEN}").json()
        ig_acc = ig_resp.get('instagram_business_account')
        if ig_acc:
            ig_id = ig_acc.get('id')
            print(f"    Instagram business account id: {ig_id}")
            updates[f"INSTA_ID_{var_base}"] = ig_id

# write updates back to .env
if updates:
    print("\nUpdating .env with detected values...")
    lines = []
    if os.path.exists('.env'):
        with open('.env') as f:
            lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            new_lines.append(line)
            continue
        if '=' in line:
            key = line.split('=',1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updates.pop(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    # append any remaining keys
    for k,v in updates.items():
        new_lines.append(f"{k}={v}\n")
    with open('.env', 'w') as f:
        f.writelines(new_lines)
    print(".env updated with the following values:")
    for k in updates:
        print(f"  {k}={updates[k]}")
else:
    print("No updates needed in .env.")

