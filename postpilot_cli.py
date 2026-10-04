"""
PostPilot Unified Command-Line Interface (postpilot_cli.py)
Consolidates token verification, Graph API page inspection, and diagnostics.

Usage:
    python postpilot_cli.py verify-token
    python postpilot_cli.py list-pages [--update-env]
    python postpilot_cli.py inspect-account
    python postpilot_cli.py health

Security Guidelines:
- Access tokens are NEVER logged or displayed in full.
- Graceful handling of unconfigured or offline credentials.
"""
import os
import sys
import json
import argparse
import datetime
import requests
from pathlib import Path
from typing import Optional, Dict, Any

import config
import database
import facebook_api
import channel_runner

GRAPH_API_VERSION = "v19.0"
BASE_GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

def mask_token(token: Optional[str]) -> str:
    """Returns a safely masked preview of a secret token."""
    if not token:
        return "[NOT SET]"
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}...{token[-4:]} (length {len(token)})"

def get_auth_token() -> Optional[str]:
    """Retrieves access token using standard config and facebook_api resolution."""
    return facebook_api.get_access_token()

# --- CLI Subcommands ---

def cmd_verify_token(args: Optional[argparse.Namespace] = None) -> int:
    """Validates the configured FB_ACCESS_TOKEN against Meta debug_token endpoint."""
    token = get_auth_token()
    if not token:
        print("[NOTICE] FB_ACCESS_TOKEN is not configured in .env or environment.")
        print("         Token verification skipped safely.")
        return 0

    print(f"[INFO] Validating configured Meta Access Token: {mask_token(token)}...")
    url = f"{BASE_GRAPH_URL}/debug_token"
    params = {'input_token': token, 'access_token': token}

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if 'error' in data:
            print(f"[API ERROR] {data['error'].get('message')}")
            return 1

        data = data.get('data', {})
        is_valid = data.get('is_valid', False)

        if is_valid:
            print("\n[VALID] Meta Access Token is VALID")
            print(f"   App ID:  {data.get('app_id')}")
            print(f"   User ID: {data.get('user_id')}")

            expires_at = data.get('expires_at', 0)
            if expires_at == 0:
                print("   Expires: Never (System/Page token)")
            else:
                exp_dt = datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc)
                print(f"   Expires: {exp_dt} UTC")

            scopes = data.get('scopes', [])
            print(f"\n[PERMISSIONS] Scopes granted ({len(scopes)}):")
            for scope in sorted(scopes):
                print(f"   - {scope}")

            critical_scopes = [
                'pages_show_list',
                'pages_read_engagement',
                'pages_manage_posts',
                'instagram_basic',
                'instagram_content_publish'
            ]
            missing = [s for s in critical_scopes if s not in scopes]
            if missing:
                print("\n[WARNING] Missing recommended scopes:")
                for m in missing:
                    print(f"   [MISSING] {m}")
            else:
                print("\n[OK] All critical permissions present.")

            # Rate limit audit via /me
            try:
                me_res = requests.get(f"{BASE_GRAPH_URL}/me", params={'access_token': token}, timeout=10)
                app_usage = me_res.headers.get('x-app-usage')
                if app_usage:
                    usage = json.loads(app_usage)
                    print(f"\n[RATE LIMIT] Call: {usage.get('call_count')}% | CPU: {usage.get('total_cputime')}% | Time: {usage.get('total_time')}%")
            except Exception:
                pass
            return 0
        else:
            print("\n[INVALID] Meta Access Token is INVALID")
            return 1
    except requests.exceptions.RequestException as e:
        print(f"[NETWORK ERROR] Failed to connect to Meta Graph API: {e}")
        return 1

def cmd_list_pages(update_env: bool = False, args: Optional[argparse.Namespace] = None) -> int:
    """Lists Facebook Pages, connected Instagram Business accounts, and WhatsApp numbers."""
    if args and hasattr(args, 'update_env'):
        update_env = args.update_env

    token = get_auth_token()
    if not token:
        print("[NOTICE] FB_ACCESS_TOKEN is not configured in .env or environment.")
        print("         Cannot fetch connected pages without credentials.")
        return 0

    print("[INFO] Querying connected Meta social assets...")
    fields = "name,id,instagram_business_account{id,username,name},whatsapp_number"
    params = {'access_token': token, 'fields': fields, 'limit': 100}

    try:
        # 1. Fetch User
        me_resp = requests.get(f"{BASE_GRAPH_URL}/me", params={'access_token': token}, timeout=10).json()
        if 'error' in me_resp:
            print(f"[API ERROR] {me_resp['error'].get('message')}")
            return 1
        print(f"[USER] {me_resp.get('name')} (ID: {me_resp.get('id')})\n")

        # 2. Fetch Accounts
        resp = requests.get(f"{BASE_GRAPH_URL}/me/accounts", params=params, timeout=10)
        data = resp.json()
        if 'error' in data:
            print(f"[API ERROR] {data['error'].get('message')}")
            return 1

        pages = data.get('data', [])
        if not pages:
            print("[INFO] No managed pages found for this user account.")
            return 0

        updates: Dict[str, str] = {}
        for i, page in enumerate(pages, 1):
            p_name = page.get('name', 'Unknown')
            p_id = page.get('id', '')
            print(f"[{i}] {p_name}")
            print(f"    Page ID:   {p_id}")

            var_base = p_name.upper().replace(' ', '_').replace('.', '_')
            updates[f"FB_PAGE_ID_{var_base}"] = p_id

            ig = page.get('instagram_business_account')
            if ig:
                ig_id = ig.get('id', '')
                ig_user = ig.get('username', '')
                print(f"    Instagram: @{ig_user} (ID: {ig_id})")
                updates[f"INSTA_ID_{var_base}"] = ig_id
            else:
                print("    Instagram: Not connected")

            wa = page.get('whatsapp_number')
            if wa:
                print(f"    WhatsApp:  {wa}")
            else:
                print("    WhatsApp:  Not linked")
            print("-" * 40)

        # 3. Optional .env update
        if update_env and updates:
            _safely_update_env(updates)

        return 0
    except requests.exceptions.RequestException as e:
        print(f"[NETWORK ERROR] Failed to fetch assets: {e}")
        return 1

def _safely_update_env(updates: Dict[str, str]):
    """Safely updates non-secret Page IDs in .env without overwriting existing secrets."""
    env_path = Path('.env')
    lines = []
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    new_lines = []
    pending_updates = dict(updates)
    for line in lines:
        stripped = line.strip()
        if '=' in stripped and not stripped.startswith('#'):
            k = stripped.split('=', 1)[0].strip()
            if k in pending_updates:
                new_lines.append(f"{k}={pending_updates.pop(k)}\n")
                continue
        new_lines.append(line)

    for k, v in pending_updates.items():
        new_lines.append(f"{k}={v}\n")

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("\n[OK] Updated .env with detected page identifiers.")

def cmd_inspect_account(args: Optional[argparse.Namespace] = None) -> int:
    """Displays user profile metadata associated with the configured token."""
    token = get_auth_token()
    if not token:
        print("[NOTICE] FB_ACCESS_TOKEN is not configured.")
        return 0

    try:
        resp = requests.get(f"{BASE_GRAPH_URL}/me?fields=id,name,email", params={'access_token': token}, timeout=10).json()
        if 'error' in resp:
            print(f"[API ERROR] {resp['error'].get('message')}")
            return 1
        print("=" * 45)
        print(" META USER ACCOUNT PROFILE")
        print("=" * 45)
        print(f"  Name:  {resp.get('name')}")
        print(f"  ID:    {resp.get('id')}")
        if resp.get('email'):
            print(f"  Email: {resp.get('email')}")
        print("=" * 45)
        return 0
    except Exception as e:
        print(f"[NETWORK ERROR] {e}")
        return 1

def cmd_health(args: Optional[argparse.Namespace] = None) -> int:
    """Runs a non-destructive system health and diagnostics audit."""
    print("=" * 55)
    print(" POSTPILOT SYSTEM HEALTH & DIAGNOSTICS")
    print("=" * 55)

    # 1. Database Check
    try:
        database.init_db()
        with database.get_db_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM posts").fetchone()
            posts_count = row['count'] if row else 0
        print(f"  [DB] SQLite/PostgreSQL Engine: OK ({posts_count} posts registered)")
    except Exception as e:
        print(f"  [DB] Engine Error: {e}")

    # 2. Worker Lease Status
    active_lease = database.get_active_worker_lease('scheduler')
    if active_lease:
        print(f"  [WORKER] Active Lease Holder: {active_lease.get('worker_id')} (expires: {active_lease.get('expires_at')})")
    else:
        print("  [WORKER] Lease Status: Idle (No active scheduler lease)")

    # 3. Configured Channels
    channels = channel_runner.list_channels()
    print(f"  [CHANNELS] Configured Channels: {len(channels)}")
    for ch in channels:
        print(f"    - {ch['name']} (Key: {ch['key']}, Page ID: {ch['page_id']})")

    # 4. Storage & Directories
    data_dir = Path(config.DATA_DIR)
    upload_dir = Path(config.UPLOAD_FOLDER)
    print(f"  [STORAGE] Data dir: {data_dir.resolve()} (exists: {data_dir.exists()})")
    print(f"  [STORAGE] Uploads dir: {upload_dir.resolve()} (exists: {upload_dir.exists()})")

    # 5. Token Status (safe preview)
    token = get_auth_token()
    print(f"  [AUTH] Meta Token: {mask_token(token)}")
    print("=" * 55)
    return 0

def main():
    parser = argparse.ArgumentParser(description="PostPilot Unified Management & Inspection CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # verify-token
    subparsers.add_parser("verify-token", help="Verify token validity and permissions with Meta Graph API")

    # list-pages
    lp = subparsers.add_parser("list-pages", help="List managed Facebook Pages, Instagram, and WhatsApp connections")
    lp.add_argument("--update-env", action="store_true", help="Automatically persist detected Page and IG IDs into .env")

    # inspect-account
    subparsers.add_parser("inspect-account", help="Display Meta user account profile details")

    # health
    subparsers.add_parser("health", help="Run comprehensive system diagnostics and readiness audit")

    parsed_args = parser.parse_args()
    if not parsed_args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        'verify-token': cmd_verify_token,
        'list-pages': cmd_list_pages,
        'inspect-account': cmd_inspect_account,
        'health': cmd_health,
    }

    cmd_func = dispatch.get(parsed_args.command)
    if cmd_func:
        exit_code = cmd_func(parsed_args)
        sys.exit(exit_code or 0)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
