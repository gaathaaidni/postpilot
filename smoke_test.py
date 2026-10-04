"""
PostPilot Smoke Test
Verifies posting modules and configuration health.
Does not post if FB_ACCESS_TOKEN is unconfigured.

Run from the project root:
    python smoke_test.py
"""
import os
import sys
from pathlib import Path
from PIL import Image

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
import database
import facebook_api

def print_header(title):
    print("\n" + "=" * 60)
    print(f" SMOKE TEST: {title.upper()}")
    print("=" * 60)

def print_result(module, result, note=""):
    status = "[SUCCESS]" if result else "[FAILED]"
    print(f"{status} {module} {note}")
    print("-" * 60)

def create_dummy_image(filename="smoke_test_image.jpg"):
    """Creates a simple dummy image for upload tests."""
    upload_dir = Path(config.UPLOAD_FOLDER)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filepath = upload_dir / filename
    try:
        img = Image.new('RGB', (200, 200), color='red')
        img.save(str(filepath))
        return filename
    except Exception as e:
        print(f"   - Failed to create dummy image: {e}")
        return None

def test_module(module_name, post_function, post_file):
    """Generic test function for Nexora and Gaatha modules."""
    print_header(module_name)
    try:
        module = __import__(post_file.replace('.py', ''))
        posts = module.load_posts()
        post = posts[0] if posts else None
        
        token = facebook_api.get_access_token()
        if not token:
            print("   - [INFO] FB_ACCESS_TOKEN not set in environment or .env")
            print("   - [INFO] Live social post skipped safely (non-destructive)")
            print_result(module_name, True, "(Skipped live post: no token)")
            return

        if not post:
            print("   - [INFO] No posts found in database for module")
            print_result(module_name, True, "(No posts in DB to test)")
            return

        print(f"   - Using post ID {post.get('id')}: {post.get('message', '')[:30]}...")
        result = getattr(module, post_function)(post['message'], post.get('image_filename', ''))
        print_result(module_name, result)
    except Exception as e:
        print(f"   - ERROR: {e}")
        print_result(module_name, False)

def main():
    print("==================================================")
    print(" PostPilot Application Module Smoke Test")
    print("==================================================")
    database.init_db()

    dummy_img = create_dummy_image("smoke_test_image.jpg")
    if not dummy_img:
        print("[WARNING] Could not create dummy image.")

    test_module("Nexora Suite (Tour)", "post_on_facebook", "nexora_suite.py")
    test_module("Nexora Phoenix (Visa)", "post_on_facebook", "nexora_by_phoenix_international.py")
    test_module("Gaatha AI", "post_to_facebook", "gaatha_loop.py")
    
    print("\nSmoke test complete.")

if __name__ == "__main__":
    main()