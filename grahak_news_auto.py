"""
Grahak Chetna - Professional News Automation
Generates structured news posts with viral hashtags and formatting.
"""
import os
import json
import requests
import random
from datetime import datetime

# Configuration
PAGE_ID = '374211199112915'

def get_token():
    if os.path.exists('token.txt'):
        with open('token.txt','r') as f: return f.read().strip()
    return os.getenv('FB_TOKEN')

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
    token = get_token()
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/feed"
    payload = {'message': message, 'access_token': token}
    try:
        r = requests.post(url, data=payload).json()
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
    # Logic to fetch from RSS or config would go here. 
    # For now, we simulate a professional update based on status.json or generic template
    
    # Example placeholder news (in production this comes from the RSS parser)
    news_items = [
        ("New Consumer Protection Rules", "The government has issued new guidelines for e-commerce platforms to prevent dark patterns."),
        ("Electric Vehicle Safety Standards", "Ministry imposes stricter battery testing norms for all new EV scooters launched in India."),
        ("Digital Payment Fraud Alert", "RBI warns users against screen-sharing apps during UPI transactions. Stay alert!")
    ]
    
    title, body = random.choice(news_items)
    message = format_news_post(title, body)
    post_text_to_fb(message)

if __name__ == "__main__":
    run_automation()