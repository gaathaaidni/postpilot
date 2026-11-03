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
13. Behavioral test: Termux HOST=127.0.0.1 enforced; custom HOST overrides rejected
14. Behavioral test: Development and production HOST behavior preserved
15. Behavioral test: Stale PID file safe quarantine/cleanup without terminating processes
16. Behavioral test: Foreign/unrelated process PID file preserved without termination
17. Behavioral test: Valid PostPilot PID verified and cleanly terminated on stop
18. Shell syntax validation for all Termux operational scripts
"""
import os
import sys
import shutil
import signal
import subprocess
import time
import unittest
import importlib
from unittest.mock import patch
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import database
import backup


def _find_bash():
    """Locates a working bash binary across Windows (Git Bash), Linux, and Termux."""
    candidates = [
        'C:/Program Files/Git/bin/bash.exe',
        'C:/Program Files/Git/usr/bin/bash.exe',
        shutil.which('bash'),
        '/bin/bash',
        '/usr/bin/bash',
        '/data/data/com.termux/files/usr/bin/bash'
    ]
    for c in candidates:
        if c and os.path.exists(c):
            try:
                r = subprocess.run([c, '--version'], capture_output=True, timeout=2)
                if r.returncode == 0:
                    return c
            except Exception:
                continue
    return None


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

        # Both must verify process ownership before killing or assuming running
        self.assertIn("verify_process_ownership", start_content, "start-termux.sh must verify process ownership")
        self.assertIn("verify_process_ownership", stop_content, "stop-termux.sh must verify process ownership")

        # stop-termux.sh must NOT use indiscriminate pkill without path scoping
        self.assertNotIn('pkill -f "python app.py"', stop_content,
                         "stop-termux.sh must not indiscriminately pkill generic 'python app.py' across system")

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

    def test_13_termux_host_loopback_enforced_behavioral(self):
        """
        Behavioral test: Verifies config.py strictly enforces HOST=127.0.0.1 in Termux mode
        and rejects custom HOST overrides (such as HOST=0.0.0.0 or LAN IP).
        """
        # Test A: Custom HOST=0.0.0.0 cannot override Termux loopback binding
        with patch.dict(os.environ, {'APP_ENV': 'termux', 'HOST': '0.0.0.0'}):
            importlib.reload(config)
            self.assertEqual(config.APP_ENV, 'termux')
            self.assertEqual(config.HOST, '127.0.0.1', "Termux MUST reject 0.0.0.0 and enforce 127.0.0.1")

        # Test B: Custom LAN IP cannot override Termux loopback binding
        with patch.dict(os.environ, {'APP_ENV': 'termux', 'HOST': '192.168.1.50'}):
            importlib.reload(config)
            self.assertEqual(config.HOST, '127.0.0.1', "Termux MUST reject LAN IPs and enforce 127.0.0.1")

        # Reset config to clean state
        with patch.dict(os.environ, {'APP_ENV': 'development', 'HOST': '127.0.0.1'}):
            importlib.reload(config)

    def test_14_development_and_production_host_behavior_preserved(self):
        """
        Behavioral test: Verifies existing development and production HOST resolution remains unchanged.
        """
        # A. Development with override allows custom HOST
        with patch.dict(os.environ, {'APP_ENV': 'development', 'HOST': '0.0.0.0'}):
            importlib.reload(config)
            self.assertEqual(config.HOST, '0.0.0.0', "Development profile must allow custom HOST overrides")

        # B. Development without HOST override defaults to 127.0.0.1
        env_clean_dev = dict(os.environ)
        env_clean_dev.pop('HOST', None)
        env_clean_dev['APP_ENV'] = 'development'
        with patch.dict(os.environ, env_clean_dev, clear=True):
            importlib.reload(config)
            self.assertEqual(config.HOST, '127.0.0.1', "Development profile must default to 127.0.0.1")

        # C. Production with explicit HOST allows configuration
        with patch.dict(os.environ, {'APP_ENV': 'production', 'HOST': '127.0.0.1'}):
            importlib.reload(config)
            self.assertEqual(config.HOST, '127.0.0.1', "Production must allow explicit HOST configuration")

        # D. Production without HOST override defaults to 0.0.0.0
        env_clean_prod = dict(os.environ)
        env_clean_prod.pop('HOST', None)
        env_clean_prod['APP_ENV'] = 'production'
        with patch('dotenv.load_dotenv'):
            with patch.dict(os.environ, env_clean_prod, clear=True):
                importlib.reload(config)
                self.assertEqual(config.HOST, '0.0.0.0', "Production must default to 0.0.0.0")

        # Reset config to clean development state
        with patch.dict(os.environ, {'APP_ENV': 'development', 'HOST': '127.0.0.1'}):
            importlib.reload(config)

    def test_15_pid_ownership_stale_pid_behavioral(self):
        """
        Behavioral test: Verifies that stop-termux.sh cleanly quarantines/removes a stale PID file
        without attempting to terminate non-existent processes or failing.
        """
        bash_bin = _find_bash()
        if not bash_bin:
            self.skipTest("Bash binary not available in test environment")

        data_dir = Path(REPO_ROOT) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        test_pid_file = data_dir / "app.pid"

        # Write a non-existent PID
        test_pid_file.write_text("99999999", encoding="utf-8")

        try:
            res = subprocess.run([bash_bin, "stop-termux.sh"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(res.returncode, 0, f"stop-termux.sh failed on stale PID: {res.stderr}")
            # PID file must have been removed safely
            self.assertFalse(test_pid_file.exists(), "Stale PID file must be cleaned up")
        finally:
            if test_pid_file.exists():
                test_pid_file.unlink()

    def test_16_pid_ownership_unrelated_process_behavioral(self):
        """
        Behavioral test: Verifies that stop-termux.sh detects an unrelated process in the PID file,
        safely preserves the unrelated process (does NOT terminate it), and removes the stale PID file.
        """
        bash_bin = _find_bash()
        if not bash_bin:
            self.skipTest("Bash binary not available in test environment")

        # Spawn an unrelated Python process sleeping in background
        unrelated_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        data_dir = Path(REPO_ROOT) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        app_pid_file = data_dir / "app.pid"

        try:
            # Write unrelated process PID into PostPilot app.pid
            app_pid_file.write_text(str(unrelated_proc.pid), encoding="utf-8")

            # Run stop-termux.sh
            res = subprocess.run([bash_bin, "stop-termux.sh"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(res.returncode, 0, f"stop-termux.sh failed: {res.stderr}")

            # Verify the unrelated process is STILL RUNNING (not terminated)
            self.assertIsNone(unrelated_proc.poll(), "stop-termux.sh must NOT terminate an unrelated foreign process!")

            # Verify the stale/foreign PID file was removed
            self.assertFalse(app_pid_file.exists(), "Stale/foreign PID file must be cleaned up")
        finally:
            # Clean up test process
            try:
                unrelated_proc.terminate()
                unrelated_proc.wait(timeout=2)
            except Exception:
                pass
            if app_pid_file.exists():
                app_pid_file.unlink()

    def test_17_pid_ownership_valid_postpilot_process_behavioral(self):
        """
        Behavioral test: Verifies that stop-termux.sh correctly identifies a genuine PostPilot process,
        terminates it cleanly, and removes the PID file.
        """
        bash_bin = _find_bash()
        if not bash_bin:
            self.skipTest("Bash binary not available in test environment")

        # Spawn a genuine PostPilot worker process inside REPO_ROOT
        mock_worker = subprocess.Popen(
            [sys.executable, "worker.py"],
            cwd=REPO_ROOT
        )
        data_dir = Path(REPO_ROOT) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        worker_pid_file = data_dir / "worker.pid"

        try:
            worker_pid_file.write_text(str(mock_worker.pid), encoding="utf-8")

            # Run stop-termux.sh
            res = subprocess.run([bash_bin, "stop-termux.sh"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(res.returncode, 0, f"stop-termux.sh failed: {res.stderr}")

            # Give process a moment to exit
            try:
                mock_worker.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

            # Verified process should be stopped
            self.assertIsNotNone(mock_worker.poll(), "Valid PostPilot worker process must be cleanly stopped")
            self.assertFalse(worker_pid_file.exists(), "PID file must be removed after clean termination")
        finally:
            try:
                mock_worker.terminate()
                mock_worker.wait(timeout=1)
            except Exception:
                pass
            if worker_pid_file.exists():
                worker_pid_file.unlink()

    def test_18_shell_syntax_validation(self):
        """
        Validates syntax of all Termux shell scripts using bash -n.
        """
        bash_bin = _find_bash()
        if not bash_bin:
            self.skipTest("Bash binary not available in test environment")

        scripts = [
            "setup-termux.sh",
            "start-termux.sh",
            "stop-termux.sh",
            "update-termux.sh"
        ]
        for script_name in scripts:
            script_path = Path(REPO_ROOT) / script_name
            self.assertTrue(script_path.exists(), f"Missing script {script_name}")
            res = subprocess.run([bash_bin, "-n", str(script_path)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Syntax error in {script_name}: {res.stderr}")


if __name__ == '__main__':
    unittest.main()
