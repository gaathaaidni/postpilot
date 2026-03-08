#!/usr/bin/env python3
"""Standalone automation: YouTube RSS -> branded image -> Facebook/Instagram."""

import os
import sys
import logging
import textwrap
import uuid
import json
from datetime import datetime

import feedparser
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# load environment
load_dotenv()

# channel id configurable
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "UC...replace_with_id")
RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"

POSTED_FILE = "posted_videos.txt"
FB_PAGE_ID = os.getenv("FB_PAGE_ID_GRAHAK_CHETNA") or os.getenv("GRAHAK_PAGE_ID") or os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
IG_USER_ID = os.getenv("INSTA_ID_GRAHAK_CHETNA") or os.getenv("IG_USER_ID")
DEFAULT_GRAHAK_PAGE_ID = "954901604381882"

# logging to console and file
ytlog = os.getenv("YT_LOG","yt.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ytlog)
    ],
)
logger = logging.getLogger(__name__)


def _resolve_asset_path(*relative_parts: str) -> str | None:
    """Resolve static asset path across local/codespace environments."""
    filename = os.path.join(*relative_parts)
    candidates = [
        filename,
        os.path.join(os.path.dirname(__file__), filename),
        os.path.join("/workspace/postpilot", filename),
        os.path.join("/workspaces/postpilot", filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _read_user_access_token() -> str | None:
    """Read long-lived user token from env or token.txt fallback."""
    env_token = os.getenv("FB_ACCESS_TOKEN")
    if env_token:
        return env_token.strip()
    try:
        with open("token.txt", "r", encoding="utf-8") as f:
            token = f.read().strip()
            return token or None
    except Exception:
        return None


def _resolve_page_access_token() -> None:
    """Resolve page token so Grahak scripts work like Nexora scripts."""
    global FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN

    if FB_PAGE_ACCESS_TOKEN and FB_PAGE_ID:
        return

    FB_PAGE_ID = FB_PAGE_ID or os.getenv("GRAHAK_PAGE_ID") or DEFAULT_GRAHAK_PAGE_ID
    user_token = _read_user_access_token()
    if not user_token:
        return

    try:
        url = "https://graph.facebook.com/v19.0/me/accounts"
        resp = requests.get(url, params={"access_token": user_token}, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        for page in data:
            if page.get("id") == FB_PAGE_ID and page.get("access_token"):
                FB_PAGE_ACCESS_TOKEN = page["access_token"]
                return
    except Exception as e:
        logger.warning(f"unable to resolve page access token from user token: {e}")


_resolve_page_access_token()

# test mode
TEST_MODE = os.getenv("TEST_MODE","False").lower() in ("1","true","yes")


def _normalize(text: str) -> str:
    return text.strip().lower()

def _text_size(draw, text, font):
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]


def _load_font(size: int, bold: bool = False):
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_logo_corner(img: Image.Image, draw: ImageDraw.ImageDraw, logo_path: str, width: int) -> None:
    if not os.path.exists(logo_path):
        return
    logo = Image.open(logo_path).convert("RGBA")
    target_w = int(width * 0.18)
    ratio = target_w / logo.width
    logo = logo.resize((target_w, int(logo.height * ratio)), Image.Resampling.LANCZOS)
    pad = 24
    x = width - logo.width - pad
    y = pad
    draw.rounded_rectangle([x - 12, y - 12, x + logo.width + 12, y + logo.height + 12], radius=16, fill=(0, 0, 0, 160))
    img.paste(logo, (x, y), logo)


def already_posted(video_id: str) -> bool:
    if not os.path.exists(POSTED_FILE):
        return False
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if _normalize(line) == _normalize(video_id):
                    return True
    except Exception as e:
        logger.error(f"error reading {POSTED_FILE}: {e}")
    return False


def mark_as_posted(video_id: str) -> None:
    try:
        with open(POSTED_FILE, "a", encoding="utf-8") as f:
            f.write(_normalize(video_id) + "\n")
    except Exception as e:
        logger.error(f"error writing to {POSTED_FILE}: {e}")


def fetch_latest_videos() -> list:
    try:
        feed = feedparser.parse(RSS_URL)
    except Exception as e:
        logger.error(f"failed to parse youtube rss: {e}")
        return []
    videos = []
    for entry in feed.entries:
        link = entry.get("link", "")
        vid = None
        if "v=" in link:
            vid = link.split("v=")[-1]
        title = entry.get("title", "")
        pub = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub = datetime(*entry.published_parsed[:6])
        videos.append({"id": vid, "title": title, "link": link, "published": pub})
    videos.sort(key=lambda x: x.get("published") or datetime.min, reverse=True)
    return videos


def create_video_image(title: str) -> str:
    width, height = 1080, 1080
    text_color = (255, 255, 255)
    bottom_h = 98
    img = Image.new("RGBA", (width, height), color=(8, 8, 12, 255))

    bg_path = _resolve_asset_path("static", "bg.png")
    if bg_path:
        bg = Image.open(bg_path).convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
        img.paste(bg, (0, 0))

    draw = ImageDraw.Draw(img, "RGBA")
    top_font = _load_font(48, bold=True)
    label_font = _load_font(52, bold=True)
    bottom_font = _load_font(42, bold=True)

    top_label = "GRAHAK CHETNA NEWS"
    tw, th = _text_size(draw, top_label, top_font)
    draw.text((44, 80), top_label, font=top_font, fill=(255, 255, 255, 235))

    badge_text = "NEWS TODAY"
    badge_w, badge_h = 430, 120
    badge_x, badge_y = (width - badge_w) // 2, int(height * 0.33)
    draw.rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], fill=(220, 36, 40))
    bdw, bdh = _text_size(draw, badge_text, label_font)
    draw.text((badge_x + (badge_w - bdw) / 2, badge_y + (badge_h - bdh) / 2 - 4), badge_text, font=label_font, fill=(255, 255, 255))

    logo_path = _resolve_asset_path("static", "logo.png")
    if logo_path:
        _draw_logo_corner(img, draw, logo_path, width)

    # auto font scaling
    max_font = 122
    min_font = 62
    lines = textwrap.wrap(title.strip(), width=15)[:4] or ["LATEST VIDEO"]

    font = _load_font(min_font, bold=True)
    widths, heights, total_h = [], [], 0
    for size in range(max_font, min_font, -2):
        test_font = _load_font(size, bold=True)
        total_h = 0
        widths=[]
        heights=[]

        for line in lines:
            bbox = draw.textbbox((0,0), line, font=test_font)
            w=bbox[2]-bbox[0]
            h=bbox[3]-bbox[1]
            widths.append(w)
            heights.append(h)
            total_h+=h+14

        if total_h < height*0.38 and max(widths) < width * 0.92:
            font=test_font
            break

    center_y = int(height*0.60)
    y = center_y - total_h//2

    for i,line in enumerate(lines):

        w=widths[i]
        h=heights[i]

        x=(width-w)//2

        draw.text((x+4,y+4),line,font=font,fill=(0,0,0))
        draw.text((x,y),line,font=font,fill=(255,255,255))

        y+=h+14



    bottom_text = "Watch on YouTube @grahakchetna"
    draw.rectangle([0, height - bottom_h, width, height], fill=(20, 20, 28, 230))
    w, h = _text_size(draw, bottom_text, bottom_font)
    draw.text(((width - w) / 2, height - bottom_h + (bottom_h - h) / 2), bottom_text, font=bottom_font, fill=text_color)

    filename = f"temp_video_{int(datetime.utcnow().timestamp())}.jpg"
    img.convert("RGB").save(filename, "JPEG", quality=95)
    return filename


def post_to_facebook_photo(image_path: str, caption: str) -> str | None:
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        logger.error("Facebook credentials missing")
        return None
    url = f"https://graph.facebook.com/{FB_PAGE_ID}/photos"
    try:
        with open(image_path, "rb") as f:
            files = {"source": f}
            data = {"caption": caption, "access_token": FB_PAGE_ACCESS_TOKEN}
            r = requests.post(url, files=files, data=data, timeout=60)
        r.raise_for_status()
        res = r.json()
        photo_id = res.get("id")
        if not photo_id:
            logger.error(f"no photo id returned: {res}")
            return None
        info = requests.get(f"https://graph.facebook.com/{photo_id}", params={"fields": "images", "access_token": FB_PAGE_ACCESS_TOKEN}, timeout=30).json()
        imgs = info.get("images", [])
        if imgs:
            return imgs[0].get("source")
        return None
    except Exception as e:
        logger.error(f"facebook upload failed: {e} - {r.text if 'r' in locals() else ''}")
        return None


def post_to_instagram_photo(image_url: str) -> bool:
    if not IG_USER_ID or not FB_PAGE_ACCESS_TOKEN:
        logger.error("Instagram credentials missing")
        return False
    create_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
    data = {"image_url": image_url, "caption": "", "access_token": FB_PAGE_ACCESS_TOKEN}
    try:
        r = requests.post(create_url, data=data, timeout=30)
        r.raise_for_status()
        container = r.json().get("id")
        if not container:
            logger.error("no container id")
            return False
        r2 = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish", data={"creation_id": container, "access_token": FB_PAGE_ACCESS_TOKEN}, timeout=30)
        r2.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"instagram post failed: {e} - {r.text if 'r' in locals() else ''}")
        return False


def run():
    vids = fetch_latest_videos()
    for v in (vids[:1] if TEST_MODE else vids):
        vid = v.get("id")
        if not vid:
            continue
        if already_posted(vid) and not TEST_MODE:
            logger.info(f"SKIPPED: {vid}")
            continue
        title = v.get("title", "")
        link = v.get("link", "")
        img = create_video_image(title)
        caption = (
            "🚨 GrahakChetna Exclusive\n\n"
            f"{title}\n\n"
            "Watch Full Video:\n"
            f"{link}\n\n"
            "#GrahakChetna #BreakingNews #IndiaNews #YouTubeNews"
        )
        try:
            if TEST_MODE:
                logger.info(f"[TEST] would post video: {title}")
                with open(ytlog,'a') as lf:
                    lf.write(f"[{datetime.now(datetime.UTC).isoformat()}] TEST - VIDEO - {title}\n")
                mark_as_posted(vid)
            else:
                fb_url = post_to_facebook_photo(img, caption)
                if fb_url:
                    try:
                        import time
                        time.sleep(2)
                    except Exception:
                        pass
                    post_to_instagram_photo(fb_url)
                mark_as_posted(vid)
                logger.info(f"VIDEO POSTED: {vid}")
        except Exception as e:
            logger.error(f"ERROR: {vid} - {e}")
        finally:
            try:
                os.remove(img)
            except Exception:
                pass
        if TEST_MODE:
            break
    logger.info(f"run complete - {'simulated' if TEST_MODE else 'done'}")


if __name__ == "__main__":
    run()
