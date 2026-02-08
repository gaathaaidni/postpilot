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

FB_PAGE_ID = '519872534547188'
FB_ACCESS_TOKEN = get_access_token()
IG_USER_ID = '17841472248438802'
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
    url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/posts?fields=id,message,attachments{{media,type}}&access_token={FB_ACCESS_TOKEN}"
    return requests.get(url).json().get('data', [])

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
