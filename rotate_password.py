#!/usr/bin/env python3
"""
PostPilot Administrator & User Password Rotation Utility
Secure CLI-only utility to rotate passwords directly in the database.

Security features:
- Uses getpass for silent input (passwords are never echoed to terminal).
- Never prints, logs, or persists plain-text passwords or hashes.
- Enforces strong password complexity policy.
- Updates only the specified existing user account.
- Zero external network dependencies.

Usage:
    python rotate_password.py
    python rotate_password.py --username admin
"""
import sys
import getpass
import argparse
from typing import Tuple

import database


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validates password against a sensible security policy:
    - Minimum 10 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number or special character
    - Rejects known default or trivial passwords
    """
    if len(password) < 10:
        return False, "Password must be at least 10 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter (A-Z)."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter (a-z)."
    if not any(c.isdigit() or not c.isalnum() for c in password):
        return False, "Password must contain at least one digit (0-9) or special symbol."
    if password.lower() in ("admin123", "admin", "password", "postpilot", "changeme", "12345678"):
        return False, "Password cannot be a known default, predictable sequence, or common word."
    return True, ""


def rotate_user_password(username: str = None) -> bool:
    """Interactively prompts for username and new password, then rotates the credential."""
    print("=" * 60)
    print(" PostPilot Secure Password Rotation Utility")
    print("=" * 60)

    # 1. Resolve username
    if not username:
        try:
            username = input("Enter username to update (e.g., admin): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[CANCELLED] Operation aborted by user.")
            return False

    if not username:
        print("[ERROR] Username cannot be blank.")
        return False

    # 2. Check if user exists in database
    user = database.get_user_by_username(username)
    if not user:
        print(f"[ERROR] User account '{username}' was not found in the database.")
        return False

    print(f"[INFO] Verified account: '{username}' (User ID: {user['id']}, Role: {user['role']})")

    # 3. Prompt for new password silently
    try:
        new_password = getpass.getpass("Enter new password: ")
    except (KeyboardInterrupt, EOFError):
        print("\n[CANCELLED] Operation aborted by user.")
        return False

    # 4. Validate password strength
    valid, err_msg = validate_password_strength(new_password)
    if not valid:
        print(f"[ERROR] Weak password: {err_msg}")
        return False

    # 5. Confirm password
    try:
        confirm_password = getpass.getpass("Confirm new password: ")
    except (KeyboardInterrupt, EOFError):
        print("\n[CANCELLED] Operation aborted by user.")
        return False

    if new_password != confirm_password:
        print("[ERROR] Passwords do not match. Please run the utility again.")
        return False

    # 6. Atomic database update
    try:
        database.update_user_password(username, new_password)
        print("=" * 60)
        print(f"[SUCCESS] Password successfully updated for user '{username}'.")
        print("[NOTICE] Old credentials have been invalidated immediately.")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update password in database: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Securely rotate PostPilot user passwords directly in the database."
    )
    parser.add_argument(
        "--username", "-u",
        help="Username of the existing account to rotate (will prompt if omitted)."
    )
    args = parser.parse_args()

    success = rotate_user_password(args.username)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

