#!/bin/bash
# ==============================================================================
# PostPilot — Automated Android / Termux Setup Script
# ==============================================================================
# Installs and configures PostPilot for native execution in Android Termux.
# Uses pre-compiled ARM64 packages to guarantee fast, reliable installation.
# ==============================================================================

set -e

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
fi

source .venv/bin/activate
pip install --upgrade pip wheel setuptools

# 4. Install Python dependencies
echo "📥 [4/6] Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt

# 5. Environment configuration (.env)
echo "⚙️ [5/6] Configuring local environment..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    # Ensure Termux specific defaults
    sed -i 's/APP_ENV=development/APP_ENV=termux/g' .env || true
    echo "   Created .env with APP_ENV=termux and LOCAL_MODE=1"
else
    echo "   Existing .env detected; preserving existing configuration."
fi

# 6. Initialize Database
echo "🗄️ [6/6] Initializing PostPilot SQLite database..."
python -c "import database; database.init_db(); print('   ✅ Database schema initialized successfully!')"

# Make scripts executable
chmod +x start-termux.sh stop-termux.sh update-termux.sh run.sh setup.sh || true

echo "======================================================="
echo " 🎉 POSTPILOT INSTALLATION COMPLETE!"
echo "======================================================="
echo " To start PostPilot on Android:"
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
