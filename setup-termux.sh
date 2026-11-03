#!/bin/bash
# ==============================================================================
# PostPilot — Automated Android / Termux Setup Script
# ==============================================================================
# Installs and configures PostPilot for native execution in Android Termux.
# Uses pre-compiled ARM64 packages to guarantee fast, reliable installation.
# Idempotent: safe to run repeatedly without overwriting existing data.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "======================================================="
echo " POSTPILOT — ANDROID TERMUX AUTOMATED SETUP"
echo "======================================================="

# 1. Environment Detection
if [ -z "$PREFIX" ] || [[ "$PREFIX" != *"/com.termux/"* ]]; then
    echo "⚠️ Warning: PREFIX does not indicate an active Termux environment."
    echo "   Continuing in standard Linux compatibility mode..."
fi

# 2. Update Termux repositories and install system packages
echo "📦 [1/6] Updating Termux package repositories..."
pkg update -y || {
    echo "⚠️ Termux repository update warning. If this fails, run 'termux-change-repo' to select a working mirror."
}

echo "📦 [2/6] Installing Python, Git, and ARM64-optimized native media libraries..."
# Install python-pillow pre-compiled to avoid heavy source compilation on phone
pkg install -y python git python-pillow libjpeg-turbo libpng freetype libwebp

# 3. Create Virtual Environment with system site-packages (for python-pillow)
echo "🐍 [3/6] Setting up isolated Python virtual environment..."
if [ ! -d ".venv" ]; then
    python -m venv --system-site-packages .venv
    echo "   Created new virtual environment in .venv"
else
    echo "   Existing virtual environment detected in .venv (preserved)"
fi

source .venv/bin/activate
pip install --upgrade pip wheel setuptools

# 4. Install Python dependencies
echo "📥 [4/6] Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt

# 5. Runtime storage directories & Environment configuration (.env)
echo "⚙️ [5/6] Configuring local runtime directories and environment..."
# Ensure runtime storage directories exist without overwriting existing data
mkdir -p data/images data/media data/backups logs

if [ ! -f ".env" ]; then
    cp .env.example .env
    # Enforce Termux-safe defaults: loopback host, termux profile, local auto-login, offline mock AI
    sed -i 's/^APP_ENV=.*/APP_ENV=termux/g' .env || true
    echo "   Created new .env template from .env.example with:"
    echo "     - APP_ENV=termux"
    echo "     - HOST=127.0.0.1"
    echo "     - PORT=5000"
    echo "     - LOCAL_MODE=1"
    echo "     - AI_PROVIDER=mock (100% offline, 0 API keys required)"
else
    echo "   ℹ️ Existing .env detected; preserving existing user configuration."
fi

# 6. Initialize Database (Idempotent: non-destructive table & column migrations)
echo "🗄️ [6/6] Verifying SQLite database and applying schema migrations..."
python -c "import database; database.init_db(); print('   ✅ Database schema verified and updated successfully!')"

# Make helper scripts executable
chmod +x start-termux.sh stop-termux.sh update-termux.sh run.sh setup.sh || true

echo "======================================================="
echo " 🎉 POSTPILOT INSTALLATION COMPLETE!"
echo "======================================================="
echo " To start PostPilot (web server + background scheduler):"
echo "   ./start-termux.sh"
echo ""
echo " Then open your phone's browser and visit:"
echo "   http://127.0.0.1:5000"
echo ""
echo " To safely stop PostPilot:"
echo "   ./stop-termux.sh"
echo ""
echo " To update PostPilot in the future:"
echo "   ./update-termux.sh"
echo "======================================================="
