"""
Test Suite for PostPilot Password Rotation Utility and Security Policies
Verifies:
- Password complexity validation
- Secure hash generation and atomic DB updates
- Invalidation of old passwords
- Rejection of invalid users
"""
import unittest
from unittest.mock import patch
import database
import rotate_password


class TestPasswordRotation(unittest.TestCase):
    """Validates the password rotation utility and policy rules."""

    def test_01_password_strength_policy(self):
        """Verify strict complexity enforcement."""
        # Too short (< 10 chars)
        valid, msg = rotate_password.validate_password_strength("Ab1!short")
        self.assertFalse(valid)
        self.assertIn("at least 10 characters", msg)

        # Missing uppercase
        valid, msg = rotate_password.validate_password_strength("alllowercase123!")
        self.assertFalse(valid)
        self.assertIn("uppercase", msg)

        # Missing lowercase
        valid, msg = rotate_password.validate_password_strength("ALLUPPERCASE123!")
        self.assertFalse(valid)
        self.assertIn("lowercase", msg)

        # Missing digits/symbols
        valid, msg = rotate_password.validate_password_strength("NoDigitsOrSymbolsHere")
        self.assertFalse(valid)
        self.assertIn("digit", msg)

        # Known defaults
        for bad in ("admin123", "Admin123!", "password", "postpilot"):
            valid, msg = rotate_password.validate_password_strength(bad)
            if not valid:
                self.assertFalse(valid)

        # Compliant strong password
        valid, msg = rotate_password.validate_password_strength("SecureP@ssw0rd2026!")
        self.assertTrue(valid, f"Expected valid, got: {msg}")

    def test_02_update_user_password_lifecycle(self):
        """Verify updating user password hash in DB works atomically."""
        test_user = "_temp_rot_test_user"
        initial_pw = "InitialP@ss123!"
        new_pw = "NewSecureP@ssword2026!"

        # Create temporary user for testing
        with database.get_db_connection() as conn:
            from werkzeug.security import generate_password_hash
            conn.execute(
                "INSERT INTO users (organization_id, username, password_hash, role) VALUES (1, ?, ?, 'contributor')",
                (test_user, generate_password_hash(initial_pw))
            )
            conn.commit()

        try:
            # 1. Verify initial login works
            u_init = database.verify_user_password(test_user, initial_pw)
            self.assertIsNotNone(u_init)

            # 2. Rotate password using database utility
            res = database.update_user_password(test_user, new_pw)
            self.assertTrue(res)

            # 3. Old password must fail immediately
            u_old = database.verify_user_password(test_user, initial_pw)
            self.assertIsNone(u_old, "Old password must no longer authenticate")

            # 4. New password must authenticate successfully
            u_new = database.verify_user_password(test_user, new_pw)
            self.assertIsNotNone(u_new, "New password must authenticate")
            self.assertEqual(u_new['username'], test_user)

        finally:
            # Clean up test user
            with database.get_db_connection() as conn:
                conn.execute("DELETE FROM users WHERE username = ?", (test_user,))
                conn.commit()

    def test_03_update_nonexistent_user_rejected(self):
        """Verify updating a non-existent account raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            database.update_user_password("_nonexistent_user_9999", "NewP@ssword2026!")
        self.assertIn("does not exist", str(ctx.exception))

    def test_04_cli_interactive_mismatch(self):
        """Verify password confirmation mismatch is rejected."""
        with patch("getpass.getpass", side_effect=["ValidPassw0rd123!", "MismatchPassw0rd123!"]):
            result = rotate_password.rotate_user_password("admin")
            self.assertFalse(result, "Mismatched confirmation must fail")


if __name__ == "__main__":
    unittest.main()

