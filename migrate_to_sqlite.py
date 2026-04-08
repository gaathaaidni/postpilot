import sqlite3
import json
import os
from pathlib import Path

ROOT = Path("/workspaces/postpilot")
DB_PATH = ROOT / "posts.db"
POSTS_DIR = ROOT / "posts"
DB_PATH = ROOT / "src" / "posts.db" # Database is now in src/
POSTS_DIR = ROOT / "posts" # JSON files for migration are assumed to be in root/posts/

FILES = {
    'tour': POSTS_DIR / "tour_posts.json",
    'nz': POSTS_DIR / "visa_posts.json",
    'tour': POSTS_DIR / "tour_posts.json", # Assuming these JSON files are still in root/posts/ for migration
    'nz': POSTS_DIR / "visa_posts.json",   # If they are moved, update this path accordingly
    'insta': POSTS_DIR / "insta_posts.json",
    'gaatha': POSTS_DIR / "gaatha_posts.json"
}

def migrate():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_type TEXT NOT NULL,
            message TEXT,
            image_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_posted_at TIMESTAMP
        )
    ''')
    
    for post_type, filepath in FILES.items():
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    posts = json.load(f)
                    for post in posts:
                        cursor.execute(
                            "INSERT INTO posts (post_type, message, image_filename) VALUES (?, ?, ?)",
                            (post_type, post.get('message'), post.get('image_filename'))
                        )
                print(f"✅ Migrated {len(posts)} posts for {post_type}")
            except Exception as e: print(f"❌ Error migrating {post_type}: {e}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()