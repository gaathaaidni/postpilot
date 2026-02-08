# insta_thread.py
import requests, time, json
from threading import Event

stop_event = Event()
status_callback = None
current_interval = 3 * 60  # Default to 3 minutes for Instagram sync

def get_access_token():
    """Read access token from token.txt file"""
    try:
        with open('token.txt', 'r') as f:
            return f.read().strip()
    except:
        return None

FB_PAGE_ID = '967550829768297'  # Nexora Suite - syncs to Instagram (fallback)
FB_PAGE_NAME = 'Nexora Investment'  # friendly page name to resolve if ID not correct
FB_ACCESS_TOKEN = get_access_token()
IG_USER_ID = '17841472248438802'  # Nexora by Phoenix Instagram (fallback)
IG_USERNAME = 'nexora.phoenix'    # Instagram username (for clarity / logging)
POSTED_FILE = 'posted.txt'

def set_status_callback(callback):
    """Set callback for status updates"""
    global status_callback
    status_callback = callback

def set_interval(interval):
    """Set sync interval in seconds"""
    global current_interval
    current_interval = interval

def get_recent_facebook_posts():
    page_id = FB_PAGE_ID
    if not page_id and FB_PAGE_NAME:
        page_id = resolve_page_id(FB_PAGE_NAME)

    url = f"https://graph.facebook.com/v18.0/{page_id}/posts?fields=id,message,attachments{{media,type}}&access_token={FB_ACCESS_TOKEN}"
    return requests.get(url).json().get('data', [])


def resolve_page_id(page_name):
    """Try to resolve a page id from a human-friendly page name using the Graph search endpoint."""
    if not FB_ACCESS_TOKEN:
        return FB_PAGE_ID
    try:
        q = requests.get(f"https://graph.facebook.com/v18.0/search?type=page&q={requests.utils.quote(page_name)}&access_token={FB_ACCESS_TOKEN}").json()
        data = q.get('data', [])
        if not data:
            return FB_PAGE_ID
        # prefer exact name match if available
        for p in data:
            if p.get('name', '').lower() == page_name.lower():
                return p.get('id')
        return data[0].get('id')
    except Exception:
        return FB_PAGE_ID


def resolve_instagram_user_id_from_page(page_id):
    """Get the connected Instagram Business account id from a Facebook Page."""
    if not FB_ACCESS_TOKEN or not page_id:
        return IG_USER_ID
    try:
        r = requests.get(f"https://graph.facebook.com/v18.0/{page_id}?fields=instagram_business_account&access_token={FB_ACCESS_TOKEN}").json()
        ig = r.get('instagram_business_account')
        if ig and 'id' in ig:
            return ig['id']
    except Exception:
        pass
    return IG_USER_ID

def get_posted_ids():
    try:
        with open(POSTED_FILE, 'r') as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_posted_id(post_id):
    with open(POSTED_FILE, 'a') as f:
        f.write(post_id + '\n')

def post_to_instagram(image_url, caption):
    create_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
    publish_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish"

    payload = {'image_url': image_url, 'caption': caption, 'access_token': FB_ACCESS_TOKEN}
    res = requests.post(create_url, data=payload).json()
    if 'id' not in res:
        return False

    time.sleep(5)
    return 'id' in requests.post(publish_url, data={'creation_id': res['id'], 'access_token': FB_ACCESS_TOKEN}).json()

def run_insta_sync():
    post_count = 0
    while not stop_event.is_set():
        try:
            # resolve page and instagram ids (allow name-based lookup)
            page_id = FB_PAGE_ID or (FB_PAGE_NAME and resolve_page_id(FB_PAGE_NAME))
            # resolve IG user id from page if possible
            global IG_USER_ID
            IG_USER_ID = resolve_instagram_user_id_from_page(page_id)

            posts = get_recent_facebook_posts()
            posted_ids = get_posted_ids()

            for post in posts:
                if stop_event.is_set():
                    break
                post_id = post['id']
                if post_id in posted_ids: continue

                media = post.get('attachments', {}).get('data', [{}])[0].get('media', {})
                if post.get('attachments', {}).get('data', [{}])[0].get('type') != 'photo':
                    continue

                image_url = media.get('image', {}).get('src')
                if image_url and post_to_instagram(image_url, post.get('message', '')):
                    post_count += 1
                    current_post_summary = f"{post.get('message', '')[:50]}..." if len(post.get('message', '')) > 50 else post.get('message', 'No message')
                    if status_callback:
                        status_callback('insta', True, f"Synced (Post #{post_count})", current_post_summary)
                    save_posted_id(post_id)

            if status_callback:
                status_callback('insta', True, 'Checking...', None)
            time.sleep(current_interval)
        except Exception as e:
            print("Error in Insta sync:", e)
            time.sleep(60)

def stop_insta_sync():
    stop_event.set()


def preview_recent_posts(limit=10):
    """Fetch recent Facebook posts and print candidate info without posting."""
    page_id = FB_PAGE_ID or (FB_PAGE_NAME and resolve_page_id(FB_PAGE_NAME))
    ig_id = resolve_instagram_user_id_from_page(page_id)
    print(f"Using FB page id: {page_id}")
    print(f"Resolved IG user id: {ig_id} (username: {IG_USERNAME})")

    posts = get_recent_facebook_posts()
    if not posts:
        print("No posts found or invalid token/page.")
        return

    for i, post in enumerate(posts[:limit], start=1):
        post_id = post.get('id')
        message = post.get('message', '')
        attachments = post.get('attachments', {}).get('data', [])
        attach = attachments[0] if attachments else {}
        media = attach.get('media', {})
        img = media.get('image', {}).get('src')
        a_type = attach.get('type')
        print(f"\nPost #{i}")
        print(f"  id: {post_id}")
        print(f"  type: {a_type}")
        print(f"  image: {img}")
        print(f"  message: {message[:200]}" if message else "  message: (none)")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Insta sync helper')
    parser.add_argument('--preview', action='store_true', help='Fetch and show recent FB posts (no posting)')
    parser.add_argument('--limit', type=int, default=10, help='Number of posts to show with --preview')
    args = parser.parse_args()

    if args.preview:
        preview_recent_posts(limit=args.limit)
