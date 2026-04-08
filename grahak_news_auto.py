"""
Grahak Chetna - Professional News Automation
Generates structured news posts with viral hashtags and formatting.
"""
import os
import json
import random
import requests
import xml.etree.ElementTree as ET
from datetime import datetime # This path needs to be updated to APP_ROOT / 'config'
import facebook_api

# Configuration
PAGE_ID = '374211199112915'

VIRAL_HASHTAGS = """
.
.
#GrahakChetna #ConsumerRights #BreakingNews #India #JagoGrahakJago 
#NewsUpdate #DailyNews #ConsumerAwareness #Trending #Latest
"""

def format_news_post(title, body, source="Grahak Chetna"):
    date_str = datetime.now().strftime("%d %b %Y")
    
    post_text = f"📢 GRAHAK CHETNA NEWS UPDATE | {date_str}\n\n"
    post_text += f"🛑 {title.upper()}\n\n"
    post_text += f"{body}\n\n"
    post_text += f"Via: {source}\n"
    post_text += VIRAL_HASHTAGS
    return post_text

def post_text_to_fb(message):
    token = facebook_api.get_access_token()
    page_token = facebook_api.get_page_token(token, PAGE_ID)
    if not page_token:
        print("❌ Could not retrieve Page Access Token")
        return False
        
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/feed"
    payload = {'message': message, 'access_token': page_token}
    try:
        r = facebook_api._request_with_retry("POST", url, data=payload)
        if 'id' in r:
            print(f"✅ News Posted: {r['id']}")
            return True
        else:
            print(f"❌ Error: {r}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def run_automation():
    # Fetch feeds from the config managed by app.py
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'rss_feeds.json')
    news_items = []

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                feeds = config.get('feeds', [])
                
            for feed in feeds:
                print(f"📡 Fetching: {feed['name']}...")
                resp = requests.get(feed['url'], timeout=10)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    # Support standard RSS 2.0
                    for item in root.findall('.//item'):
                        title = item.find('title').text if item.find('title') is not None else ""
                        desc = item.find('description').text if item.find('description') is not None else ""
                        if title:
                            news_items.append((title, desc, feed['name']))
        except Exception as e:
            print(f"❌ RSS Fetch Error: {e}")

    if not news_items:
        print("⚠️ No news found in RSS feeds. Using fallback placeholders.")
        news_items = [
            ("Consumer Awareness Drive", "Stay informed about your rights as a consumer in the digital age.", "System"),
            ("Safety First", "Always check for ISI marks and quality certifications before purchasing appliances.", "System")
        ]
    
    # Select a random news item from collected feeds
    title, body, source = random.choice(news_items)
    # Clean HTML tags if present in description
    import re
    clean_body = re.sub('<[^<]+?>', '', body)[:300] + "..." if body else ""
    
    message = format_news_post(title, clean_body, source)
    post_text_to_fb(message)

if __name__ == "__main__":
    run_automation()