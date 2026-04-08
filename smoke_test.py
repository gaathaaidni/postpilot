"""
PostPilot Smoke Test

This script runs a series of high-level tests to verify that all major
posting modules in the application are functioning correctly.

Run from the project root:
    python smoke_test.py
"""

import os
import sys
import json
from PIL import Image

# Add current dir to path to ensure modules are found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- Helper Functions ---
def print_header(title):
    print("\n" + "="*60)
    print(f" SMOKE TEST: {title.upper()}")
    print("="*60)

def print_result(module, result):
    if result:
        print(f"✅ {module}: SUCCESS")
    else:
        print(f"❌ {module}: FAILED")
    print("-" * 60)

def get_first_post(filepath):
    """Safely gets the first post from a JSON file."""
    try:
        with open(filepath, 'r') as f:
            posts = json.load(f)
        return posts[0] if posts else None
    except Exception as e:
        print(f"   - Error loading {filepath}: {e}")
        return None

def create_dummy_image(filename="smoke_test_image.jpg"):
    """Creates a simple dummy image for upload tests."""
    if not os.path.exists("images"):
        os.makedirs("images")
    filepath = os.path.join("images", filename)
    try:
        img = Image.new('RGB', (200, 200), color = 'red')
        img.save(filepath)
        print(f"   - Created dummy image: {filepath}")
        return filepath
    except Exception as e:
        print(f"   - Failed to create dummy image: {e}")
        return None

# --- Test Functions ---

def test_module(module_name, post_function, post_file):
    """Generic test function for Nexora and Gaatha modules."""
    print_header(module_name)
    try:
        module = __import__(post_file.replace('.py', ''))
        post = get_first_post(module.POSTS_FILE)
        if not post:
            print_result(module_name, False)
            return
        
        print(f"   - Using post: {post['message'][:30]}...")
        print("   - ⚠️ WARNING: This will attempt a REAL post.")
        
        # Dynamically call the post function from the imported module
        result = getattr(module, post_function)(post['message'], post['image_filename'])
        print_result(module_name, result)
    except Exception as e:
        print(f"   - CRITICAL ERROR: {e}")
        print_result(module_name, False)

def test_grahak_uploader():
    print_header("Grahak Uploader")
    try:
        import grahak_uploader
        dummy_image_path = create_dummy_image()
        if not dummy_image_path:
            print_result("Grahak Uploader", False)
            return

        caption = "Smoke test for Grahak Uploader."
        targets = {'fb_feed': True} # Test one target
        print("   - Uploading dummy image to FB Feed...")
        result = grahak_uploader.process_upload(dummy_image_path, caption, targets)
        print(f"   - API Response: {result}")
        success = 'fb_feed' in result and result['fb_feed'] == 'Success'
        print_result("Grahak Uploader", success)
        
        if os.path.exists(dummy_image_path):
            os.remove(dummy_image_path)
    except Exception as e:
        print(f"   - CRITICAL ERROR: {e}")
        print_result("Grahak Uploader", False)

def main():
    print("🔥 PostPilot Application Smoke Test 🔥")
    
    # Create shared dummy image for all tests
    dummy_img = create_dummy_image("smoke_test_image.jpg")
    if not dummy_img: print("⚠️ Warning: Could not create dummy image. Upload tests may fail.")

    test_module("Nexora Suite (Tour)", "post_on_facebook", "nexora_suite.py")
    test_module("Nexora Phoenix (Visa)", "post_on_facebook", "nexora_by_phoenix_international.py")
    test_module("Gaatha AI", "post_to_facebook", "gaatha_loop.py")
    test_grahak_uploader()
    
    print("\nSmoke test complete. Review the output for any 'FAILED' or 'CRITICAL ERROR' messages.")

if __name__ == "__main__":
    main()