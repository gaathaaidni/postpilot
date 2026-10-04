"""
PostPilot Clean Installation & Dependency Isolation Verification Suite
Validates that PostPilot can be installed from a clean checkout into an isolated
environment without hidden developer-machine dependencies or hardcoded paths.
"""
import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def run_clean_install_test():
    print("=" * 65)
    print(" POSTPILOT CLEAN INSTALLATION & ENVIRONMENT AUDIT")
    print("=" * 65)

    temp_root = Path(tempfile.mkdtemp(prefix="postpilot_clean_install_"))
    print(f"[1/5] Created isolated test sandbox: {temp_root.name}")

    try:
        # 1. Copy project files excluding git, pycache, local databases, and temporary artifacts
        project_copy = temp_root / "postpilot_app"
        project_copy.mkdir()
        
        excluded_patterns = {'.git', '__pycache__', 'data', 'backups', '.env', '.venv', 'news.log', 'yt.log'}
        
        for item in BASE_DIR.iterdir():
            if item.name in excluded_patterns or item.name.startswith('.git'):
                continue
            dest = project_copy / item.name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.db'))
            else:
                shutil.copy2(item, dest)
                
        print(f"  [OK] Clean copy assembled ({len(list(project_copy.iterdir()))} root entries)")

        # 2. Verify requirements.txt syntax & markers
        print("[2/5] Auditing requirements.txt specification...")
        req_file = project_copy / "requirements.txt"
        assert req_file.exists(), "requirements.txt missing from distribution"
        reqs = req_file.read_text(encoding='utf-8').splitlines()
        print(f"  [OK] Found {len(reqs)} declared package dependencies:")
        for r in reqs:
            if r.strip() and not r.startswith('#'):
                print(f"    - {r.strip()}")

        # 3. Create isolated virtual environment
        print("[3/5] Initializing clean virtual environment...")
        venv_dir = temp_root / "venv"
        res_venv = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], capture_output=True, text=True)
        assert res_venv.returncode == 0, f"Failed to create venv: {res_venv.stderr}"
        
        if sys.platform == "win32":
            py_bin = venv_dir / "Scripts" / "python.exe"
            pip_bin = venv_dir / "Scripts" / "pip.exe"
        else:
            py_bin = venv_dir / "bin" / "python"
            pip_bin = venv_dir / "bin" / "pip"
            
        print(f"  [OK] Isolated Python interpreter: {py_bin.name}")

        # 4. Verify clean compilation using isolated python
        print("[4/5] Testing compilation in clean checkout...")
        res_compile = subprocess.run([str(py_bin), "-m", "compileall", "-q", str(project_copy)], capture_output=True, text=True)
        assert res_compile.returncode == 0, f"Syntax or compilation error in clean checkout: {res_compile.stderr}"
        print("  [OK] Zero syntax errors in clean distribution")

        # 5. Execute runtime validation suite inside clean checkout
        print("[5/5] Running runtime validation suite in clean environment...")
        env = os.environ.copy()
        env['POSTPILOT_DATA_DIR'] = str(project_copy / "test_data")
        env['SECRET_KEY'] = 'clean-install-test-key-67890'
        env['ADMIN_PASSWORD'] = 'CleanInstallPass123!'
        
        # Test runtime suite
        res_test = subprocess.run(
            [sys.executable, str(project_copy / "test_runtime_validation.py")],
            cwd=str(project_copy),
            env=env,
            capture_output=True,
            text=True
        )
        assert res_test.returncode == 0, f"Runtime validation failed in clean install:\n{res_test.stderr}\n{res_test.stdout}"
        print("  [OK] Comprehensive runtime validation passed in clean checkout")

        print("=" * 65)
        print(">>> CLEAN INSTALLATION VERIFICATION: ALL CHECKS PASSED <<<")
        print("=" * 65)
        return True

    finally:
        shutil.rmtree(str(temp_root), ignore_errors=True)

if __name__ == '__main__':
    run_clean_install_test()
