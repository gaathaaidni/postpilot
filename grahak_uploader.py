"""
/workspaces/postpilot/grahak_uploader.py
"""
import os
import time
import requests
import json

# Configuration
PAGE_ID = os.getenv('FB_PAGE_ID_GRAHAK_CHETNA') or '374211199112915'
IG_USER_ID = os.getenv('INSTA_ID_GRAHAK_CHETNA')

def get_access_token():
    token = os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN')
    if not token and os.path.exists('token.txt'):
        try:
            with open('token.txt', 'r') as f:
                token = f.read().strip()
        except: pass
    return token

def get_page_token(user_token):
    """Exchange User Token for Page Token to ensure we post AS THE PAGE"""
    try:
        url = f"https://graph.facebook.com/v19.0/me/accounts"
        params = {"access_token": user_token}
        resp = requests.get(url, params=params).json()
        for page in resp.get("data", []):
            if page.get("id") == PAGE_ID:
                return page.get("access_token")
    except Exception:
        pass
    return user_token  # Fallback to original if exchange fails

def upload_fb_video(file_path, caption, published=True, token=None):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/videos"
    with open(file_path, 'rb') as f:
        data = {
            'description': caption,
            'published': str(published).lower(),
            'access_token': token 
        }
        files = {'source': (os.path.basename(file_path), f, 'video/mp4')}
        return requests.post(url, data=data, files=files).json()

def upload_fb_photo(file_path, caption, published=True, token=None):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
    with open(file_path, 'rb') as f:
        data = {
            'message': caption,
            'published': str(published).lower(),
            'access_token': token 
        }
        files = {'source': (os.path.basename(file_path), f, 'image/jpeg')}
        return requests.post(url, data=data, files=files).json()

def upload_fb_story(file_path, is_video, token=None):
    endpoint = "video_stories" if is_video else "photo_stories"
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/{endpoint}"
    with open(file_path, 'rb') as f:
        data = {'access_token': token }
        # For video stories, the key is video_data; for photos, it's source
        file_key = 'video_data' if is_video else 'source'
        mime_type = 'video/mp4' if is_video else 'image/jpeg'
        
        files = {file_key: (os.path.basename(file_path), f, mime_type)}
        return requests.post(url, data=data, files=files).json()

def get_public_url(media_id, is_video, token=None):
    """Get a public source URL from a Facebook upload for Instagram ingestion"""
    fields = 'source' if is_video else 'images'
    url = f"https://graph.facebook.com/v19.0/{media_id}?fields={fields}&access_token={token}"
    
    for _ in range(5): # Retry loop for video processing
        try:
            res = requests.get(url).json()
            if is_video and 'source' in res:
                return res['source']
            if not is_video and 'images' in res and res['images']:
                return res['images'][0]['source']
        except: pass
        time.sleep(3)
    return None

def publish_instagram(url, caption, is_video, is_reel, token=None):
    if not IG_USER_ID: return {'error': 'No IG ID'}
    
    # 1. Create Container
    create_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    payload = {
        'access_token': token,
        'caption': caption
    }
    
    if is_video:
        payload['video_url'] = url
        payload['media_type'] = 'REELS' if is_reel else 'VIDEO'
    else:
        payload['image_url'] = url
        # media_type defaults to IMAGE
    
    res = requests.post(create_url, data=payload).json()
    if 'id' not in res:
        return {'error': f"Container failed: {res}"}
    
    container_id = res['id']
    
    # 2. Publish
    time.sleep(3) # Wait for container readiness
    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(publish_url, data={'creation_id': container_id, 'access_token': token}).json()
    return pub_res

def process_upload(file_path, caption, targets):
    token = get_access_token()
    # Try to get the specific Page Token for Facebook operations
    # This ensures the post appears as "Grahak Chetna" and not the System User
    page_token = get_page_token(token)
    
    is_video = file_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
    results = {}
    
    # --- Facebook Feed ---
    fb_id = None
    if targets.get('fb_feed'):
        print("📤 Posting to FB Feed...")
        if is_video:
            res = upload_fb_video(file_path, caption, True, page_token)
        else:
            res = upload_fb_photo(file_path, caption, True, page_token)
        
        if 'id' in res:
            fb_id = res['id']
            results['fb_feed'] = 'Success'
        else:
            results['fb_feed'] = f"Failed: {res}"
            
    # --- Facebook Story ---
    if targets.get('fb_story'):
        print("📤 Posting to FB Story...")
        res = upload_fb_story(file_path, is_video, page_token)
        if 'id' in res or 'post_id' in res:
            results['fb_story'] = 'Success'
        else:
            results['fb_story'] = f"Failed: {res}"
            
    # --- Instagram ---
    if targets.get('ig_feed') or targets.get('ig_reel'):
        print("Preparing Instagram...")
        # We need a public URL. Reuse FB upload or create temp one.
        public_url = None
        
        if fb_id:
            public_url = get_public_url(fb_id, is_video, page_token)
        
        if not public_url:
            print("📤 Uploading unpublished to FB for hosting...")
            # Upload hidden to get URL
            if is_video:
                res = upload_fb_video(file_path, caption, False, page_token)
            else:
                res = upload_fb_photo(file_path, caption, False, page_token)
            
            if 'id' in res:
                public_url = get_public_url(res['id'], is_video, page_token)
        
        if public_url:
            print("📤 Posting to Instagram...")
            is_reel = targets.get('ig_reel', False)
            # Use main token for Insta, or page_token also works if linked correctly
            res = publish_instagram(public_url, caption, is_video, is_reel, page_token)
            key = 'ig_reel' if is_reel else 'ig_feed'
            if 'id' in res:
                results[key] = 'Success'
            else:
                results[key] = f"Failed: {res}"
        else:
            results['instagram'] = "Failed to generate public URL"
            
    return results