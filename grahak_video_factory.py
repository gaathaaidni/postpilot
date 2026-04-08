"""
Grahak Chetna - Video News Factory
Integrates video generation code with Facebook & Instagram Reels publishing.
"""
import os
import time
import json
from . import facebook_api
try:
    from gtts import gTTS
except ImportError:
    print("⚠️ gTTS library not found. Install with: pip install gTTS")
    gTTS = None
import textwrap
from PIL import Image, ImageDraw, ImageFont
try:
    from moviepy.editor import AudioFileClip, ImageClip
except ImportError:
    print("⚠️ MoviePy library not found. Install with: pip install moviepy")
    AudioFileClip = None

# --- Configuration ---
PAGE_ID = os.getenv('FB_PAGE_ID_GRAHAK_CHETNA') or '374211199112915'
IG_USER_ID = os.getenv('INSTA_ID_GRAHAK_CHETNA')

# Global Font Cache to reduce disk I/O
_FONT_CACHE = {}

# --- Language Helpers ---
def _resolve_asset_path(*relative_parts):
    """Resolve static asset path across local/codespace environments."""
    filename = os.path.join(*relative_parts)
    candidates = [
        filename,
        os.path.join(os.path.dirname(__file__), filename), # Current directory (src/)
        os.path.join(os.path.dirname(os.path.dirname(__file__)), filename), # Project root
    ]
    # Also check within src/static if it's a static asset
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def _load_font(size, bold=False):
    """Load a scalable TrueType font."""
    cache_key = (size, bold)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    # Common font paths
    candidates = [
        os.getenv("GRAHAK_FONT_PATH"),
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[cache_key] = font
                return font
            except:
                continue

    return ImageFont.load_default()

def _text_size(draw, text, font):
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

def _draw_logo_corner(img, draw, width):
    logo_path = _resolve_asset_path("static", "logo.png") or _resolve_asset_path("static", "gclogo.jpg")
    if not logo_path or not os.path.exists(logo_path):
        return

    logo = Image.open(logo_path).convert("RGBA")
    diameter = int(width * 0.16)
    logo = logo.resize((diameter, diameter), Image.Resampling.LANCZOS)

    # circular crop for logo
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    circle_logo = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    circle_logo.paste(logo, (0, 0), mask)

    pad = 24
    x = width - diameter - pad
    y = pad
    draw.ellipse([x - 10, y - 10, x + diameter + 10, y + diameter + 10], fill=(0, 0, 0, 170))
    img.paste(circle_logo, (x, y), circle_logo)

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
def generate_video_from_text(title, script, lang='en', background_image=None, fps=5):
    """
    Generates a reel-style video from title and description.
    Returns the local file path of the generated video.
    """
    print(f"🎬 Starting Video Generation: {title} [{lang}]")
    
    # 1. Generate Audio (Proof of Multi-Language Support)
    audio_file = generate_audio(f"{title}. {script}", lang=lang)
    if not audio_file:
        print("❌ Failed to generate audio.")
        return None
    
    output_filename = f"news_{int(time.time())}.mp4"
    image_filename = f"temp_frame_{int(time.time())}.jpg"
    
    # 2. Generate Layout Image (Grahak Chetna Style)
    width, height = 1080, 1080
    img = Image.new("RGBA", (width, height), color=(8, 8, 12, 255))

    # Background
    if background_image and os.path.exists(background_image):
        bg = Image.open(background_image).convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
        img.paste(bg, (0, 0))
    else:
        # Prioritize shortbg, then fall back to bg
        bg_path = _resolve_asset_path("static", "shortbg.png") or \
                  _resolve_asset_path("static", "shortbg.jpg") or \
                  _resolve_asset_path("static", "bg.png")
        if bg_path:
            bg = Image.open(bg_path).convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
            img.paste(bg, (0, 0))

    # Anchor Image (Overlay)
    anchor_path = _resolve_asset_path("static", "anchor.png")
    if anchor_path:
        try:
            anchor = Image.open(anchor_path).convert("RGBA")
            # Resize anchor if too large (max 50% of height)
            if anchor.height > height * 0.5:
                ratio = (height * 0.5) / anchor.height
                anchor = anchor.resize((int(anchor.width * ratio), int(height * 0.5)), Image.Resampling.LANCZOS)
            # Position: Bottom Right
            img.paste(anchor, (width - anchor.width, height - anchor.height), anchor)
        except Exception as e:
            print(f"⚠️ Could not load anchor image: {e}")

    draw = ImageDraw.Draw(img, "RGBA")
    
    # Fonts
    top_font = _load_font(48, bold=True)
    label_font = _load_font(52, bold=True)
    bottom_font = _load_font(42, bold=True)
    
    # Header
    top_label = "News Updates"
    draw.text((44, 140), top_label, font=top_font, fill=(255, 255, 255, 220))

    # Badge
    badge_text = "GRAHAK CHETNA"
    badge_w, badge_h = 620, 96
    badge_x, badge_y = (width - badge_w) // 2, 26
    draw.rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], fill=(220, 36, 40))
    bdw, bdh = _text_size(draw, badge_text, label_font)
    draw.text((badge_x + (badge_w - bdw) / 2, badge_y + (badge_h - bdh) / 2 - 4), badge_text, font=label_font, fill=(255, 255, 255))

    # Logo
    _draw_logo_corner(img, draw, width)

    # Title (Wrapped in Rounded Rects)
    lines = textwrap.wrap(title.strip(), width=18)[:5]
    
    # Dynamic font sizing
    font_size = 60 if len(lines) < 3 else 48
    font = _load_font(font_size, bold=True)
    
    center_y = int(height * 0.60)
    line_heights = [_text_size(draw, line, font)[1] for line in lines]
    total_h = sum(line_heights) + (len(lines) - 1) * 24
    y = center_y - total_h // 2

    for line in lines:
        w, h = _text_size(draw, line, font)
        x = (width - w) // 2
        draw.rounded_rectangle([x - 22, y - 8, x + w + 22, y + h + 10], radius=14, fill=(0, 0, 0, 160))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += h + 24

    # Footer
    bottom_h = 150
    draw.rectangle([0, height - bottom_h, width, height], fill=(20, 20, 28, 230))
    bottom_text = "Watch @grahakchetna"
    w, h = _text_size(draw, bottom_text, bottom_font)
    draw.text(((width - w) / 2, height - bottom_h + 50), bottom_text, font=bottom_font, fill=(255, 255, 255))

    # Save Image
    img.convert("RGB").save(image_filename, "JPEG", quality=95)
    
    # 3. Create Video with MoviePy
    if AudioFileClip:
        try:
            print("🎞️ Rendering video clip...")
            audio_clip = AudioFileClip(audio_file)
            image_clip = ImageClip(image_filename).set_duration(audio_clip.duration + 0.5)
            
            video = image_clip.set_audio(audio_clip)
            video.write_videofile(output_filename, fps=fps, codec="libx264", audio_codec="aac", logger=None)
            
            # Cleanup
            os.remove(image_filename)
            os.remove(audio_file)
            
        except Exception as e:
            print(f"❌ Video encoding failed: {e}")
            # Ensure cleanup on failure
            for f in [image_filename, audio_file]:
                if f and os.path.exists(f):
                    try: os.remove(f)
                    except: pass
            return None
    else:
        print("⚠️ MoviePy missing, returning image only.")
        return image_filename # Fallback to just image if no moviepy
    
    if not os.path.exists(output_filename):
        print("⚠️ Warning: Video file was not created by the generation script.")
        return None
        
    return output_filename

# --- 2. Facebook Publishing ---
def post_video_to_facebook(video_path, caption):
    token = facebook_api.get_access_token()
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/videos"
    
    print("📤 Uploading to Facebook...")
    try:
        with open(video_path, 'rb') as f:
            files = {'source': (os.path.basename(video_path), f, 'video/mp4')}
            data = {
                'description': caption,
                'access_token': token
            }
            res_json = facebook_api._request_with_retry("POST", url, files=files, data=data)
            
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
        
    token = facebook_api.get_access_token()
    
    # Step A: Get Public URL from Facebook Video
    print("🔄 Fetching video URL for Instagram...")
    time.sleep(10) # Wait for FB processing
    
    vid_url = f"https://graph.facebook.com/v19.0/{fb_video_id}?fields=source&access_token={token}"
    vid_info = facebook_api._request_with_retry("GET", vid_url)
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
    res = facebook_api._request_with_retry("POST", create_url, data=payload)
    
    if 'id' not in res:
        print(f"❌ Insta Container Error: {res}")
        return False
        
    container_id = res['id']
    
    # Step C: Publish
    print("🚀 Publishing to Instagram...")
    time.sleep(5) # Wait for container readiness
    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = facebook_api._request_with_retry("POST", publish_url, data={'creation_id': container_id, 'access_token': token})
    
    if 'id' in pub_res:
        print(f"✅ Instagram Reel Posted. ID: {pub_res['id']}")
        return True
    else:
        print(f"❌ Insta Publish Error: {pub_res}")
        return False

# --- Workflow Orchestrator ---
def run_video_news_workflow(title, script, caption, hashtags, lang='en', image_filename=None):
    # 1. Generate
    bg_path = None
    if image_filename:
        # Assumes images are in 'images/' folder relative to workspace root or script
        bg_path = os.path.abspath(os.path.join("images", image_filename))
        
    video_path = generate_video_from_text(title, script, lang, bg_path)
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