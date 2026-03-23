# insta_thread.py
import requests, time, json, os
import threading

status_callback = None

def get_access_token():
    """Read user access token from env, then token.txt fallback."""
    return os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN') or _read_token_file()

def _read_token_file():
    try:
        with open('token.txt', 'r') as f:
            return f.read().strip()
    except:
        return None

POSTED_FILE = 'posted.txt'

def set_status_callback(callback):
    """Set callback for status updates"""
    global status_callback
    status_callback = callback

class InstaSync:
    def __init__(self, page_id, ig_user_id, name="Insta"):
        self.page_id = page_id
        self.ig_user_id = ig_user_id
        self.name = name
        self.stop_event = threading.Event()
        self.interval = 3 * 60
        self.access_token = get_access_token()

    def set_interval(self, seconds):
        self.interval = seconds

    def stop(self):
        self.stop_event.set()

    def get_recent_facebook_posts(self):
        url = f"https://graph.facebook.com/v18.0/{self.page_id}/posts?fields=id,message,attachments{{media,type}}&access_token={self.access_token}"
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

    def post_to_instagram(self, image_url, caption):
        if not self.ig_user_id: return False
        create_url = f"https://graph.facebook.com/v18.0/{self.ig_user_id}/media"
        publish_url = f"https://graph.facebook.com/v18.0/{self.ig_user_id}/media_publish"

        payload = {'image_url': image_url, 'caption': caption, 'access_token': self.access_token}
        res = requests.post(create_url, data=payload).json()
        if 'id' not in res:
            return False

        time.sleep(5)
        return 'id' in requests.post(publish_url, data={'creation_id': res['id'], 'access_token': self.access_token}).json()

    def run(self):
        post_count = 0
        while not self.stop_event.is_set():
            try:
                posts = self.get_recent_facebook_posts()
                posted_ids = get_posted_ids()

                for post in posts:
                    if self.stop_event.is_set(): break
                    post_id = post['id']
                    if post_id in posted_ids: continue

                    attachments = post.get('attachments', {}).get('data', [{}])[0]
                    media = attachments.get('media', {})
                    if attachments.get('type') != 'photo': continue

                    image_url = media.get('image', {}).get('src')
                    if image_url and self.post_to_instagram(image_url, post.get('message', '')):
                        post_count += 1
                        summary = f"{post.get('message', '')[:30]}..."
                        if status_callback:
                            status_callback(self.name, True, f"Synced #{post_count}", summary)
                        save_posted_id(post_id)

                if status_callback:
                    status_callback(self.name, True, 'Checking...', None)
                time.sleep(self.interval)
            except Exception as e:
                print(f"Error in {self.name} sync: {e}")
                time.sleep(60)
