"""
/workspaces/postpilot/grahak_uploader.py
"""
import os
import requests
import time
import json
import logging
import facebook_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PAGE_ID = os.getenv('FB_PAGE_ID_GRAHAK_CHETNA') or '374211199112915'
IG_USER_ID = os.getenv('INSTA_ID_GRAHAK_CHETNA')

def upload_fb_video(file_path, caption, published=True, token=None):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/videos"
    data = {
        'description': caption,
        'published': str(published).lower(),
        'access_token': token 
    }
    with open(file_path, 'rb') as f:
        files = {'source': (os.path.basename(file_path), f, 'video/mp4')}
        return facebook_api._request_with_retry("POST", url, data=data, files=files)

def upload_fb_photo(file_path, caption, published=True, token=None):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
    data = {
        'message': caption,
        'published': str(published).lower(),
        'access_token': token 
    }
    with open(file_path, 'rb') as f:
        files = {'source': (os.path.basename(file_path), f, 'image/jpeg')}
        return facebook_api._request_with_retry("POST", url, data=data, files=files)

def upload_fb_story(file_path, is_video, token=None):
    endpoint = "video_stories" if is_video else "photo_stories"
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/{endpoint}"
    data = {'access_token': token }
    file_key = 'video_data' if is_video else 'source'
    mime_type = 'video/mp4' if is_video else 'image/jpeg'
    
    with open(file_path, 'rb') as f:
        files = {file_key: (os.path.basename(file_path), f, mime_type)}
        return facebook_api._request_with_retry("POST", url, data=data, files=files)

def get_public_url(media_id, is_video, token=None):
    """Get a public source URL from a Facebook upload for Instagram ingestion"""
    fields = 'source' if is_video else 'images'
    url = f"https://graph.facebook.com/v19.0/{media_id}?fields={fields}&access_token={token}"
    
    for _ in range(20): # Retry loop for video processing (up to 100s)
        try:
            res = facebook_api._request_with_retry("GET", url)
            if is_video and 'source' in res:
                return res['source']
            if not is_video and 'images' in res and res['images']:
                return res['images'][0]['source']
        except: pass
        time.sleep(5)
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

    res = facebook_api._request_with_retry("POST", create_url, data=payload)
    if not res or 'id' not in res:
        return {'error': f"Container failed: {res}"}
    
    container_id = res['id']
    
    # 2. Publish
    # Poll for container readiness
    status_url = f"https://graph.facebook.com/v19.0/{container_id}?fields=status_code&access_token={token}"
    for _ in range(facebook_api.MAX_RETRIES * 2): # Allow more retries for status check
        time.sleep(3)
        stat = facebook_api._request_with_retry("GET", status_url)
        if stat.get('status_code') == 'FINISHED':
            break
        if stat.get('status_code') == 'ERROR':
            return {'error': f"Container Error: {stat}"}
            
    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = facebook_api._request_with_retry("POST", publish_url, data={'creation_id': container_id, 'access_token': token})
    return pub_res

def process_upload(file_path, caption, targets, callback=None): # Callback now handles progress
    # Helper to send updates to the callback
    def send_update(status_message, progress_percentage, results_data=None):
        if callback:
            update_data = {'status': status_message, 'progress': progress_percentage}
            if results_data:
                update_data['results'] = results_data
            callback(update_data)

    token = facebook_api.get_access_token()
    # Try to get the specific Page Token for Facebook operations
    # This ensures the post appears as "Grahak Chetna" and not the System User
    page_token = facebook_api.get_page_token(token, PAGE_ID)
    
    is_video = file_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
    results = {}
    
    send_update("Initializing upload process", 0)

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
            send_update("Facebook Feed uploaded", 25)
        else:
            results['fb_feed'] = f"Failed: {res}"
            send_update("Facebook Feed upload failed", 25, results)
            
    # --- Facebook Story ---
    if targets.get('fb_story'):
        send_update("Uploading to Facebook Story", 30)
        print("📤 Posting to FB Story...")
        res = upload_fb_story(file_path, is_video, page_token)
        if 'id' in res or 'post_id' in res:
            results['fb_story'] = 'Success'
            send_update("Facebook Story uploaded", 50)
        else:
            results['fb_story'] = f"Failed: {res}"
            
    # --- Instagram ---
    if targets.get('ig_feed') or targets.get('ig_reel'):
        print("Preparing Instagram...")
        # We need a public URL. Reuse FB upload or create temp one.
        public_url = None
        send_update("Preparing Instagram post", 55)
        
        if fb_id:
            public_url = get_public_url(fb_id, is_video, page_token)
        
        if not public_url:
            send_update("Uploading unpublished to Facebook for Instagram hosting", 60)
            print("📤 Uploading unpublished to FB for hosting...")
            # Upload hidden to get URL
            if is_video:
                res = upload_fb_video(file_path, caption, False, page_token)
            else:
                res = upload_fb_photo(file_path, caption, False, page_token)
            
            if 'id' in res:
                public_url = get_public_url(res['id'], is_video, page_token)
        
        if public_url:
            send_update("Publishing to Instagram", 75)
            print("📤 Posting to Instagram...")
            is_reel = targets.get('ig_reel', False)
            # Use main token for Insta, or page_token also works if linked correctly
            res = publish_instagram(public_url, caption, is_video, is_reel, page_token)
            key = 'ig_reel' if is_reel else 'ig_feed'
            if 'id' in res:
                results[key] = 'Success'
                send_update("Instagram published", 95)
            else:
                results[key] = f"Failed: {res}"
        else:
            results['instagram'] = "Failed to generate public URL"
            
    send_update("Upload process completed", 100, results) # Final update with results
    return results