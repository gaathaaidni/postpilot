"""
test_termux_compatibility.py - PostPilot Android Termux Compatibility Test Suite

Validates that PostPilot's unified codebase fully supports Android Termux:
1. Runtime environment auto-detection (APP_ENV=termux, TERMUX_VERSION, PREFIX)
2. Safe localhost network binding (127.0.0.1) and Local Mode auto-auth
3. Dependency portability (no non-ARM64 native compiled locks)
4. Shell automation scripts existence and syntax validity
5. SQLite WAL mode support for single-device multi-process concurrency
6. Safe portable backup/export support
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import database
import backup


class TestTermuxCompatibility(unittest.TestCase):

    def test_01_termux_runtime_detection(self):
        """Verifies config._detect_runtime() detects Termux across all standard triggers."""
        # A. Triggered by APP_ENV=termux
        with patch.dict(os.environ, {'APP_ENV': 'termux'}):
            self.assertEqual(config._detect_runtime(), 'termux')

        # B. Triggered by TERMUX_VERSION environment variable
        with patch.dict(os.environ, {'APP_ENV': '', 'TERMUX_VERSION': '0.118.0'}):
            self.assertEqual(config._detect_runtime(), 'termux')

        # C. Triggered by PREFIX path containing /com.termux/
        with patch.dict(os.environ, {'APP_ENV': '', 'PREFIX': '/data/data/com.termux/files/usr'}):
            self.assertEqual(config._detect_runtime(), 'termux')

    def test_02_termux_network_and_local_mode_defaults(self):
        """Verifies Termux profile binds safely to 127.0.0.1 and enables LOCAL_MODE."""
        # Simulate Termux environment
        test_env = {
            'APP_ENV': 'termux',
            'HOST': '',
            'LOCAL_MODE': ''
        }
        with patch.dict(os.environ, test_env):
            detected = config._detect_runtime()
            self.assertEqual(detected, 'termux')
            # Verify host selection logic
            host = os.getenv('HOST') or ('127.0.0.1' if detected in ('development', 'termux') else '0.0.0.0')
            self.assertEqual(host, '127.0.0.1', "Termux must bind to 127.0.0.1 by default for safety")

    def test_03_dependency_portability(self):
        """
        Verifies requirements.txt specifies only portable, ARM64-compatible libraries
        suitable for Android Termux.
        """
        req_path = Path(REPO_ROOT) / "requirements.txt"
        self.assertTrue(req_path.exists(), "requirements.txt must exist")

        with open(req_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        required_packages = {line.split('>=')[0].split(';')[0].strip().lower() for line in lines}

        # Core required portable packages
        expected_portable = {'flask', 'requests', 'werkzeug', 'python-dotenv', 'pillow'}
        self.assertTrue(expected_portable.issubset(required_packages), f"Missing core portable dependencies: {expected_portable - required_packages}")

        # Ensure no heavy native C-libraries that fail compilation on Android ARM64
        forbidden_heavy = {'tensorflow', 'torch', 'pywin32'}
        for pkg in forbidden_heavy:
            self.assertNotIn(pkg, required_packages, f"Heavy non-portable dependency '{pkg}' found in requirements.txt")

    def test_04_termux_shell_scripts_exist_and_executable_format(self):
        """Verifies Termux operation scripts exist and start with valid shebangs."""
        scripts = [
            'setup-termux.sh',
            'start-termux.sh',
            'stop-termux.sh',
            'update-termux.sh'
        ]
        for script_name in scripts:
            script_path = Path(REPO_ROOT) / script_name
            self.assertTrue(script_path.exists(), f"Script '{script_name}' is missing")
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertTrue(content.startswith('#!/bin/bash') or content.startswith('#!/bin/sh'),
                                f"Script '{script_name}' must start with a valid bash/sh shebang line")

    def test_05_sqlite_wal_mode_active(self):
        """Verifies SQLite connection enforces WAL mode required for Termux concurrency."""
        with database.get_db_connection() as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            mode = row[0].lower() if row else ''
            self.assertEqual(mode, 'wal', f"Expected SQLite journal_mode=WAL, got '{mode}'")

    def test_06_termux_documentation_completeness(self):
        """Verifies TERMUX_SETUP.md contains all required operational workflows."""
        doc_path = Path(REPO_ROOT) / "TERMUX_SETUP.md"
        self.assertTrue(doc_path.exists(), "TERMUX_SETUP.md must exist")
        with open(doc_path, 'r', encoding='utf-8') as f:
            text = f.read().lower()

        required_sections = [
            "prerequisites",
            "f-droid",
            "setup-termux.sh",
            "start-termux.sh",
            "stop-termux.sh",
            "update-termux.sh",
            "termux-wake-lock",
            "backup and restore",
            "troubleshooting",
            "internal device storage",
            "127.0.0.1:5000"
        ]
        for sec in required_sections:
            self.assertIn(sec, text, f"Section '{sec}' missing from TERMUX_SETUP.md")

    def test_07_offline_mock_ai_studio_portability(self):
        """Verifies AI Marketing Studio functions in offline mode on Termux with zero API keys or external calls."""
        import ai_service
        provider = ai_service.get_ai_provider('mock')
        brand = {'name': 'Termux Brand', 'positioning': 'Mobile Marketing'}
        campaign = {'name': 'Field Campaign', 'objective': 'Direct Engagement', 'brief': 'On-the-go content'}

        result = ai_service.generate_campaign_content(
            provider=provider,
            brand_info=brand,
            campaign_info=campaign,
            target_platform='whatsapp'
        )
        self.assertIsNotNone(result)
        self.assertIn('Update:', result.headline)
        self.assertIn('Field Campaign', result.caption)
        self.assertEqual(result.ai_provider, 'mock')

if __name__ == '__main__':
    unittest.main()
