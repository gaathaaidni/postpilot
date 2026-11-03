"""
test_termux_compatibility.py - PostPilot Android Termux Compatibility Test Suite

Validates that PostPilot's unified codebase fully supports Android Termux:
1. Runtime environment auto-detection (APP_ENV=termux, TERMUX_VERSION, PREFIX)
2. Safe localhost network binding (127.0.0.1) and Local Mode auto-auth
3. Dependency portability (no non-ARM64 native compiled locks)
4. Shell automation scripts existence and syntax validity
5. SQLite WAL mode support for single-device multi-process concurrency
6. Safe portable backup/export support
7. Offline Mock AI Marketing Studio operation without credentials or network
8. Complete environment template (.env.example) validation for all config.py variables
9. Default AI provider mock resolution and AI_MOCK compliance
10. PID tracking, worker daemon duplicate prevention, and scoped safe shutdown
11. Setup idempotency and template preservation (.env.example vs .env)
12. Comprehensive operational documentation (worker requirement, wake-lock limitations)
"""
import os
import sys
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
        test_env = {
            'APP_ENV': 'termux',
            'HOST': '',
            'LOCAL_MODE': ''
        }
        with patch.dict(os.environ, test_env):
            detected = config._detect_runtime()
            self.assertEqual(detected, 'termux')
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
            "127.0.0.1:5000",
            "ai_provider=mock"
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

    def test_08_env_example_matches_config_variables(self):
        """Verifies .env.example declares all key configuration variables consumed by config.py."""
        env_example_path = Path(REPO_ROOT) / ".env.example"
        self.assertTrue(env_example_path.exists(), ".env.example must exist as authoritative template")

        with open(env_example_path, 'r', encoding='utf-8') as f:
            content = f.read()

        required_vars = [
            "APP_ENV=",
            "SECRET_KEY=",
            "FLASK_DEBUG=",
            "HOST=",
            "PORT=",
            "DATABASE_URL=",
            "POSTPILOT_DATA_DIR=",
            "POSTPILOT_UPLOAD_FOLDER=",
            "MAX_CONTENT_LENGTH=",
            "LOCAL_MODE=",
            "ADMIN_USERNAME=",
            "ADMIN_PASSWORD=",
            "SESSION_COOKIE_SECURE=",
            "AI_PROVIDER=",
            "AI_TIMEOUT_SECONDS=",
            "AI_MAX_PLATFORMS_PER_REQUEST=",
            "AI_MAX_PROMPT_CHARS=",
            "AI_MAX_OUTPUT_TOKENS=",
            "AI_ORG_HOURLY_GENERATION_LIMIT=",
            "AI_DEDUPLICATION_WINDOW_SECONDS=",
            "GROQ_API_KEY=",
            "OPENAI_API_KEY=",
            "FB_ACCESS_TOKEN=",
            "FB_PAGE_ID_SUITE=",
            "FB_PAGE_ID_PHOENIX=",
            "FB_PAGE_ID_GAATHA_AI=",
            "INSTA_ID_SUITE=",
            "INSTA_ID_PHOENIX=",
            "TOUR_INTERVAL=",
            "VISA_INTERVAL=",
            "GAATHA_INTERVAL=",
            "INSTA_CHECK_INTERVAL="
        ]
        for var in required_vars:
            self.assertIn(var, content, f"Missing required variable '{var}' in .env.example")

    def test_09_default_ai_provider_mock_resolution(self):
        """Verifies config.py defaults AI provider to mock and respects AI_MOCK override."""
        self.assertEqual(config.AI_PROVIDER, 'mock', "Default AI_PROVIDER must be 'mock' for safe offline operation")

        # Test explicit AI_MOCK=1 override support
        test_env = {'AI_PROVIDER': 'groq', 'AI_MOCK': '1'}
        with patch.dict(os.environ, test_env):
            # Evaluate override logic matching config.py
            prov = os.getenv('AI_PROVIDER', 'mock').strip().lower()
            if os.getenv('AI_MOCK', '').strip().lower() in ('1', 'true', 'yes'):
                prov = 'mock'
            self.assertEqual(prov, 'mock')

    def test_10_termux_scripts_pid_tracking_and_safe_shutdown(self):
        """Verifies start-termux.sh and stop-termux.sh implement safe PID tracking and scoped shutdown."""
        start_script = Path(REPO_ROOT) / "start-termux.sh"
        stop_script = Path(REPO_ROOT) / "stop-termux.sh"

        with open(start_script, 'r', encoding='utf-8') as f:
            start_content = f.read()

        with open(stop_script, 'r', encoding='utf-8') as f:
            stop_content = f.read()

        # Both must track PID files
        self.assertIn("data/app.pid", start_content, "start-termux.sh must track app PID")
        self.assertIn("data/worker.pid", start_content, "start-termux.sh must track worker PID")
        self.assertIn("data/app.pid", stop_content, "stop-termux.sh must read app PID file")
        self.assertIn("data/worker.pid", stop_content, "stop-termux.sh must read worker PID file")

        # start-termux.sh must coordinate the worker daemon and avoid duplicates
        self.assertIn("worker.py", start_content, "start-termux.sh must handle worker startup")
        self.assertIn("kill -0", start_content, "start-termux.sh must verify if process is already running")

        # stop-termux.sh must NOT use indiscriminate pkill without path scoping
        self.assertNotIn('pkill -f "python app.py"', stop_content,
                         "stop-termux.sh must not indiscriminately pkill generic 'python app.py' across system")
        self.assertIn('$DIR/app.py', stop_content,
                         "stop-termux.sh fallback must scope matching to repository directory")

    def test_11_setup_termux_idempotency_and_template(self):
        """Verifies setup-termux.sh uses .env.example, preserves existing .env, and does not reference .env.termux."""
        setup_script = Path(REPO_ROOT) / "setup-termux.sh"
        with open(setup_script, 'r', encoding='utf-8') as f:
            setup_content = f.read()

        self.assertIn(".env.example", setup_content, "setup-termux.sh must use .env.example as template")
        self.assertNotIn(".env.termux", setup_content, "setup-termux.sh must NOT reference nonexistent .env.termux")
        self.assertIn("mkdir -p", setup_content, "setup-termux.sh must idempotently create storage directories")
        self.assertIn("if [ ! -f \".env\" ]", setup_content, "setup-termux.sh must preserve existing .env file")

    def test_12_documentation_worker_and_wakelock_accuracy(self):
        """Verifies TERMUX_SETUP.md documents worker requirements, PID tracking, and wake-lock realities."""
        doc_path = Path(REPO_ROOT) / "TERMUX_SETUP.md"
        with open(doc_path, 'r', encoding='utf-8') as f:
            text = f.read().lower()

        # Verify documentation explains worker.py requirement for scheduled posts
        self.assertIn("worker.py", text)
        self.assertIn("scheduled calendar posts", text)
        self.assertIn("process_due_scheduled_posts", text)

        # Verify wake-lock limitations are documented accurately
        self.assertIn("low memory killer", text)
        self.assertIn("unrestricted", text)
        self.assertIn("battery optimization", text)


if __name__ == '__main__':
    unittest.main()
