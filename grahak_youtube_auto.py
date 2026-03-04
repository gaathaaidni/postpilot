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
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

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

# test mode
TEST_MODE = os.getenv("TEST_MODE","False").lower() in ("1","true","yes")


def _normalize(text: str) -> str:
    return text.strip().lower()

def _text_size(draw, text, font):
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]


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
    bg_color = (80, 10, 10)
    text_color = (255, 255, 255)
    bottom_h = 80
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except Exception:
        font = ImageFont.load_default()

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    top_label = "GRAHAK CHETNA NEWS"
    y = 40
    draw.text((40, y), top_label, font=font, fill=text_color)
    _, th = _text_size(draw, top_label, font)
    y += th + 20

    lines = textwrap.wrap(title, width=30)
    for line in lines:
        if y > height - bottom_h - 100:
            break
        draw.text((40, y), line, font=font, fill=text_color)
        _, lh = _text_size(draw, line, font)
        y += lh + 10

    bottom_text = "Watch on YouTube @grahakchetna"
    w, h = draw.textsize(bottom_text, font=font)
    draw.text(((width - w) / 2, height - bottom_h + (bottom_h - h) / 2), bottom_text, font=font, fill=text_color)

    filename = f"temp_video_{int(datetime.utcnow().timestamp())}.jpg"
    img.save(filename, "JPEG")
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
                    lf.write(f"[{datetime.utcnow().isoformat()}] TEST - VIDEO - {title}\n")
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
