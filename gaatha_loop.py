import time, json, os
import threading
import random
import facebook_api
import posting_utils

# Gaatha AI Settings (now relative to src/)
PAGE_ID = os.getenv('FB_PAGE_ID_GAATHA_AI') or os.getenv('FB_PAGE_ID_GAATHA') or '1028368893692590'
POST_TYPE = "gaatha"

ACCESS_TOKEN = facebook_api.get_access_token()
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
    return posting_utils.load_posts(POST_TYPE)

def post_to_facebook(message, image_filename):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
    
    # Construct absolute image path
    image_path = os.path.join(os.path.dirname(__file__), 'images', image_filename)
    
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return False

    page_token = facebook_api.get_page_token(ACCESS_TOKEN, PAGE_ID)
    if not page_token:
        print("Gaatha Post Error: Could not get page token")
        return False

    try:
        with open(image_path, 'rb') as img_file:
            payload = {
                'caption': message,
                'access_token': page_token
            }
            files = {
                'source': img_file
            }
            result = facebook_api._request_with_retry("POST", url, data=payload, files=files)
            
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
        posts = posting_utils.load_posts(POST_TYPE)
        if posts:
            post = posts[0] # Priority post
            msg = post.get('message', 'Gaatha AI Update')
            img = post.get('image_filename', '')
            
            if status_callback:
                status_callback('gaatha', True, 'Posting...', msg)
            
            if post_to_facebook(msg, img):
                posting_utils.update_last_posted_timestamp(post.get('id'))
                if status_callback:
                    status_callback('gaatha', True, 'Posted Successfully', msg)
            else:
                if status_callback:
                    status_callback('gaatha', True, 'Post Failed', msg)
        else:
            if status_callback:
                status_callback('gaatha', True, 'No posts defined', None)
                
        # Wait in small increments to remain responsive to stop_event
        wait_until = time.time() + current_interval
        while time.time() < wait_until and not stop_event.is_set():
            time.sleep(5)

def stop_gaatha_loop():
    stop_event.set()