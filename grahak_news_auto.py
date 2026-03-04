#!/usr/bin/env python3
"""Standalone automation: RSS news -> breaking image -> Facebook+Instagram."""

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

# configuration paths
CONFIG_FEEDS = os.path.join("config", "rss_feeds.json")
STATUS_FILE = os.path.join("config", "automation_status.json")

POSTED_FILE = "posted_news.txt"
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

# ensure config directory exists
os.makedirs(os.path.dirname(CONFIG_FEEDS), exist_ok=True)

# default RSS list used if config missing
DEFAULT_FEEDS = [
    {"name": "Google News India", "url": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"},
    {"name": "ANI News", "url": "https://www.aninews.in/rss/"},
]

# test mode flag
TEST_MODE = os.getenv("TEST_MODE", "False").lower() in ("1","true","yes")

# logging to both console and file
logfile = os.getenv("NEWS_LOG", "news.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(logfile)
    ],
)
logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return text.strip().lower()


def already_posted(title: str) -> bool:
    if not os.path.exists(POSTED_FILE):
        return False
    norm = _normalize(title)
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if _normalize(line) == norm:
                    return True
    except Exception as e:
        logger.error(f"error reading {POSTED_FILE}: {e}")
    return False


def mark_as_posted(title: str) -> None:
    try:
        with open(POSTED_FILE, "a", encoding="utf-8") as f:
            f.write(_normalize(title) + "\n")
    except Exception as e:
        logger.error(f"error writing to {POSTED_FILE}: {e}")


def load_feeds_from_config() -> list:
    try:
        with open(CONFIG_FEEDS, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("feeds", DEFAULT_FEEDS)
    except Exception:
        with open(CONFIG_FEEDS, "w", encoding="utf-8") as f:
            json.dump({"feeds": DEFAULT_FEEDS}, f, indent=2)
        return DEFAULT_FEEDS


def load_status() -> dict:
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        status = {
            "news_enabled": True,
            "youtube_enabled": True,
            "last_news_run": "",
            "last_youtube_run": "",
            "last_news_post": "",
            "last_youtube_post": "",
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
        return status


def save_status(status: dict) -> None:
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        logger.error(f"failed to write status: {e}")


def fetch_rss_news() -> list:
    feeds = load_feeds_from_config()
    items = []
    for source in feeds:
        try:
            feed = feedparser.parse(source.get("url", ""))
        except Exception as e:
            logger.error(f"failed to parse feed {source.get('name')}: {e}")
            continue
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            items.append(
                {
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": published,
                    "source": source.get("name", ""),
                }
            )
    items.sort(key=lambda x: x.get("published") or datetime.min, reverse=True)
    return items


def _draw_gradient(img, start, end):
    w, h = img.size
    for i in range(h):
        r = int(start[0] + (end[0]-start[0]) * (i/h))
        g = int(start[1] + (end[1]-start[1]) * (i/h))
        b = int(start[2] + (end[2]-start[2]) * (i/h))
        ImageDraw.Draw(img).line([(0, i),(w, i)], fill=(r,g,b))

def _text_size(draw, text, font):
    bbox = draw.textbbox((0,0), text, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]


def create_news_image(title: str, source: str) -> str:
    width, height = 1080, 1080
    # gradient background
    img = Image.new("RGB", (width, height), color=0)
    _draw_gradient(img, (80,10,10), (0,0,0))  # dark red -> black
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except Exception:
        font = ImageFont.load_default()

    # top banner
    banner_h = 100
    draw.rectangle([0,0,width,banner_h], fill=(20,20,20))
    banner_text = "GRAHAK CHETNA NEWS"
    bw, bh = _text_size(draw, banner_text, font)
    draw.text(((width-bw)/2, (banner_h-bh)/2), banner_text, font=font, fill=(255,255,255))

    # breaking badge
    badge_w, badge_h = 140, 40
    draw.rectangle([20, 20, 20+badge_w, 20+badge_h], fill=(200,0,0))
    bdw, bdh = _text_size(draw, "BREAKING", font)
    draw.text((20+(badge_w-bdw)/2, 20+(badge_h-bdh)/2), "BREAKING", font=font, fill=(255,255,255))

    # headline with shadow
    lines = textwrap.wrap(title, width=30)
    y = banner_h + 40
    for line in lines:
        if y > height - 120:
            break
        # shadow
        draw.text((40+2, y+2), line, font=font, fill=(0,0,0))
        draw.text((40, y), line, font=font, fill=(255,255,255))
        _, lh = _text_size(draw, line, font)
        y += lh + 10

    # watermark
    wm_text = "GRAHAK CHETNA"
    wmw, wmh = _text_size(draw, wm_text, font)
    draw.text((width-wmw-20, height-wmh-120), wm_text, font=font, fill=(255,255,255,50))

    # bottom strip
    bottom_strip_h = 80
    draw.rectangle([0, height - bottom_strip_h, width, height], fill=(30,30,30))
    source_text = f"Courtesy: {source}"
    w, h = _text_size(draw, source_text, font)
    draw.text(((width - w) / 2, height - bottom_strip_h + (bottom_strip_h - h) / 2), source_text, font=font, fill=(255,255,255))

    filename = f"temp_{uuid.uuid4().hex}.jpg"
    img.save(filename, "JPEG")
    return filename


def post_to_facebook_photo(image_path: str, caption: str) -> str | None:
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        logger.error("Facebook credentials not set")
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
        images = info.get("images", [])
        if images:
            return images[0].get("source")
        return None
    except Exception as e:
        logger.error(f"facebook photo upload failed: {e} - {r.text if 'r' in locals() else ''}")
        return None


def post_to_instagram_photo(image_url: str) -> bool:
    if not IG_USER_ID or not FB_PAGE_ACCESS_TOKEN:
        logger.error("Instagram credentials not set")
        return False
    create_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
    data = {"image_url": image_url, "caption": "", "access_token": FB_PAGE_ACCESS_TOKEN}
    try:
        r = requests.post(create_url, data=data, timeout=30)
        r.raise_for_status()
        container = r.json().get("id")
        if not container:
            logger.error("no container id returned for instagram")
            return False
        pub_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish"
        r2 = requests.post(pub_url, data={"creation_id": container, "access_token": FB_PAGE_ACCESS_TOKEN}, timeout=30)
        r2.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"instagram photo post failed: {e} - {r.text if 'r' in locals() else ''}")
        return False


def run():
    status = load_status()
    status["last_news_run"] = datetime.utcnow().isoformat()
    save_status(status)

    items = fetch_rss_news()
    posted = 0
    last_title = ""
    for item in items[:1] if TEST_MODE else items:
        title = item.get("title", "")
        link = item.get("link", "")
        source = item.get("source", "")
        if already_posted(title) and not TEST_MODE:
            continue
        img_path = create_news_image(title, source)
        caption = (
            "🚨 Breaking News\n\n"
            f"{title}\n\n"
            "Read full report:\n"
            f"{link}\n\n"
            f"Courtesy: {source}\n\n"
            "#GrahakChetna #BreakingNews #IndiaNews #Trending"
        )
        try:
            if TEST_MODE:
                logger.info(f"[TEST] would post news: {title}")
                with open(logfile, 'a') as lf:
                    lf.write(f"[{datetime.utcnow().isoformat()}] TEST - NEWS - {title}\n")
                posted += 1
                last_title = title
            else:
                fb_image_url = post_to_facebook_photo(img_path, caption)
                if fb_image_url:
                    try:
                        import time
                        time.sleep(2)
                    except Exception:
                        pass
                    post_to_instagram_photo(fb_image_url)
                mark_as_posted(title)
                last_title = title
                posted += 1
        except Exception as e:
            logger.error(f"error posting item '{title}': {e}")
        finally:
            try:
                os.remove(img_path)
            except Exception:
                pass
        if TEST_MODE:
            break
    if last_title and not TEST_MODE:
        status = load_status()
        status["last_news_post"] = last_title
        save_status(status)
    logger.info(f"done. {'simulated' if TEST_MODE else 'posted'} {posted} items.")


if __name__ == "__main__":
    run()