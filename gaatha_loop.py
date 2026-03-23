import requests, time, json, os
import threading
import random

# Gaatha AI Settings
PAGE_ID = '1028368893692590'

def get_access_token():
    token = os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN')
    if not token and os.path.exists('token.txt'):
        with open('token.txt', 'r') as f:
            token = f.read().strip()
    return token

ACCESS_TOKEN = get_access_token()
POSTS_FILE = os.path.join("posts", "gaatha_posts.json")

stop_event = threading.Event()
status_callback = None
current_interval = 30 * 60

def set_status_callback(callback):
    global status_callback
    status_callback = callback

def set_interval(interval):
    global current_interval
    current_interval = interval

def load_posts():
    try:
        with open(POSTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def post_to_facebook(message, image_filename):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
    
    # Construct absolute image path
    image_path = os.path.join(os.path.dirname(__file__), 'images', image_filename)
    
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return False

    try:
        with open(image_path, 'rb') as img_file:
            payload = {
                'message': message,
                'access_token': ACCESS_TOKEN
            }
            files = {
                'source': img_file
            }
            resp = requests.post(url, data=payload, files=files)
            result = resp.json()
            
            if 'id' in result:
                return True
            else:
                print(f"Gaatha Post Error: {result}")
                return False
    except Exception as e:
        print(f"Exception posting to Gaatha: {e}")
        return False

def run_gaatha_loop():
    while not stop_event.is_set():
        posts = load_posts()
        if posts:
            post = random.choice(posts)
            msg = post.get('message', 'Gaatha AI Update')
            img = post.get('image_filename', '')
            
            if status_callback:
                status_callback('gaatha', True, 'Posting...', msg)
            
            if post_to_facebook(msg, img):
                if status_callback:
                    status_callback('gaatha', True, 'Posted Successfully', msg)
            else:
                if status_callback:
                    status_callback('gaatha', True, 'Post Failed', msg)
        else:
            if status_callback:
                status_callback('gaatha', True, 'No posts defined', None)
                
        # Wait for interval or stop event
        stop_event.wait(current_interval)

def stop_gaatha_loop():
    stop_event.set()