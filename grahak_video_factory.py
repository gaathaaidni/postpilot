"""
Grahak Chetna - Video News Factory
Integrates video generation code with Facebook & Instagram Reels publishing.
"""
import os
import time
import requests
import json
try:
    from gtts import gTTS
except ImportError:
    print("⚠️ gTTS library not found. Install with: pip install gTTS")
    gTTS = None

# --- Configuration ---
PAGE_ID = os.getenv('FB_PAGE_ID_GRAHAK_CHETNA') or '374211199112915'
IG_USER_ID = os.getenv('INSTA_ID_GRAHAK_CHETNA')

def get_access_token():
    token = os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN')
    if not token and os.path.exists('token.txt'):
        with open('token.txt', 'r') as f:
            token = f.read().strip()
    return token

# --- Language Helpers ---
def get_font_for_lang(lang):
    """Returns a recommended font path for the given language."""
    # You must ensure these fonts exist in your environment/container
    if lang == 'hi': # Hindi
        return "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" 
    elif lang == 'gu': # Gujarati
        return "/usr/share/fonts/truetype/noto/NotoSansGujarati-Bold.ttf"
    return "arial.ttf" # English/Default

def generate_audio(text, lang='en', filename='temp_audio.mp3'):
    """Generates audio from text using gTTS (Supports 'en', 'hi', 'gu')."""
    if not gTTS:
        return None
    
    try:
        print(f"🎤 Generating TTS for lang='{lang}'...")
        # gTTS supports 'hi' (Hindi), 'gu' (Gujarati), 'en' (English)
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(filename)
        return filename
    except Exception as e:
        print(f"❌ TTS Generation Failed: {e}")
        return None

# --- 1. Video Generation (Your Code Integration) ---
def generate_video_from_text(title, script, lang='en'):
    """
    Generates a reel-style video from title and description.
    Returns the local file path of the generated video.
    """
    print(f"🎬 Starting Video Generation: {title} [{lang}]")
    
    # 1. Generate Audio (Proof of Multi-Language Support)
    audio_file = generate_audio(f"{title}. {script}", lang=lang)
    if audio_file:
        print(f"✅ Audio generated: {audio_file}")
    
    output_filename = f"news_{int(time.time())}.mp4"
    
    # =================================================================================
    # TODO: INTEGRATE YOUR EXISTING VIDEO GENERATION CODE HERE
    # Use 'title' and 'script' variables.
    # Save the final video to 'output_filename'.
    # Use 'lang' to switch fonts or styles.
    # =================================================================================
    
    # Example structure (pseudo-code):
    # my_video_lib.create_reel(
    #     heading=title,
    #     body=script,
    #     language=lang,
    #     background="news_bg.mp4",
    #     output=output_filename
    # )
    
    if not os.path.exists(output_filename):
        print("⚠️ Warning: Video file was not created by the generation script.")
        return None
        
    return output_filename

# --- 2. Facebook Publishing ---
def post_video_to_facebook(video_path, caption):
    token = get_access_token()
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/videos"
    
    print("📤 Uploading to Facebook...")
    try:
        with open(video_path, 'rb') as f:
            files = {'source': (os.path.basename(video_path), f, 'video/mp4')}
            data = {
                'description': caption,
                'access_token': token
            }
            response = requests.post(url, files=files, data=data)
            res_json = response.json()
            
            if 'id' in res_json:
                print(f"✅ Facebook Video Posted. ID: {res_json['id']}")
                return res_json['id']
            else:
                print(f"❌ Facebook Upload Error: {res_json}")
                return None
    except Exception as e:
        print(f"❌ Exception uploading to FB: {e}")
        return None

# --- 3. Instagram Publishing (Via FB Hosting) ---
def post_video_to_instagram(fb_video_id, caption):
    """
    Uses the Facebook video source as the URL for Instagram upload.
    Note: This requires the FB video to be processed and have a public source link.
    """
    if not IG_USER_ID:
        print("⚠️ Instagram ID not set. Skipping Insta upload.")
        return False
        
    token = get_access_token()
    
    # Step A: Get Public URL from Facebook Video
    print("🔄 Fetching video URL for Instagram...")
    time.sleep(10) # Wait for FB processing
    
    vid_url = f"https://graph.facebook.com/v19.0/{fb_video_id}?fields=source&access_token={token}"
    vid_info = requests.get(vid_url).json()
    video_source_url = vid_info.get('source')
    
    if not video_source_url:
        print("❌ Could not retrieve video source URL from Facebook.")
        return False
        
    # Step B: Create Container
    print("📤 Creating Instagram Container...")
    create_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    payload = {
        'media_type': 'REELS',
        'video_url': video_source_url,
        'caption': caption,
        'access_token': token
    }
    res = requests.post(create_url, data=payload).json()
    
    if 'id' not in res:
        print(f"❌ Insta Container Error: {res}")
        return False
        
    container_id = res['id']
    
    # Step C: Publish
    print("🚀 Publishing to Instagram...")
    time.sleep(5) # Wait for container readiness
    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(publish_url, data={'creation_id': container_id, 'access_token': token}).json()
    
    if 'id' in pub_res:
        print(f"✅ Instagram Reel Posted. ID: {pub_res['id']}")
        return True
    else:
        print(f"❌ Insta Publish Error: {pub_res}")
        return False

# --- Workflow Orchestrator ---
def run_video_news_workflow(title, script, caption, hashtags, lang='en'):
    # 1. Generate
    video_path = generate_video_from_text(title, script, lang)
    if not video_path:
        return False
        
    full_caption = f"📢 {title}\n\n{caption}\n\n{hashtags}"
    
    # 2. Post to FB
    fb_id = post_video_to_facebook(video_path, full_caption)
    
    # 3. Post to Insta (if FB success)
    if fb_id:
        post_video_to_instagram(fb_id, full_caption)
    
    # Cleanup
    try:
        # Optional: Keep file or delete
        # os.remove(video_path)
        pass
    except:
        pass
    
    return True