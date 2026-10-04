"""
PostPilot Legacy Migration Utility (Archived / Historical Reference)
-------------------------------------------------------------------
NOTE: This is a one-time migration script used to transition legacy JSON-based
posts from pre-v1.0 PostPilot installations into the unified SQLite/PostgreSQL database.

Active PostPilot runtime does not read from or write to JSON files.
All active posts, timestamps, and task states are managed authoritatively via database.py.
This script is preserved for historical recovery of older JSON backups if required.
"""
import json
from pathlib import Path
import config
import database

POSTS_DIR = config.BASE_DIR / "posts"

FILES = {
    'tour': POSTS_DIR / "tour_posts.json",
    'nz': POSTS_DIR / "visa_posts.json",
    'insta': POSTS_DIR / "insta_posts.json",
    'gaatha': POSTS_DIR / "gaatha_posts.json"
}

def migrate():
    database.init_db()
    with database.get_db_connection() as conn:
        for post_type, filepath in FILES.items():
            if filepath.exists():
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        posts = json.load(f)
                        count = 0
                        for post in posts:
                            msg = post.get('message', '').strip()
                            img = post.get('image_filename', '').strip()
                            if msg or img:
                                conn.execute(
                                    "INSERT INTO posts (post_type, message, image_filename) VALUES (?, ?, ?)",
                                    (post_type, msg, img)
                                )
                                count += 1
                        print(f"✅ Migrated {count} posts for {post_type}")
                except Exception as e:
                    print(f"❌ Error migrating {post_type}: {e}")
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()