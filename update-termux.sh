#!/bin/bash
# ==============================================================================
# PostPilot — Termux Git-Based Safe Update Script
# ==============================================================================
# Performs safe backup, pulls latest code from GitHub, updates dependencies,
# and applies safe non-destructive database migrations.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "======================================================="
echo " POSTPILOT — SAFE UPDATE WORKFLOW"
echo "======================================================="

# 1. Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 2. Pre-update Safety Backup
echo "📦 [1/4] Generating pre-update safety backup..."
python backup.py export

# 3. Pull latest release from authoritative GitHub repository
echo "📥 [2/4] Pulling latest verified changes from GitHub..."
git pull origin main

# 4. Update dependencies
echo "🔧 [3/4] Checking and updating Python dependencies..."
pip install -r requirements.txt

# 5. Apply safe non-destructive database migrations
echo "🗄️ [4/4] Applying database schema migrations..."
python -c "import database; database.init_db(); print('   ✅ Database schema verified and updated!')"

CURRENT_COMMIT=$(git rev-parse --short HEAD)
echo "======================================================="
echo " 🎉 PostPilot successfully updated to commit: ${CURRENT_COMMIT}"
echo " Start the application with: ./start-termux.sh"
echo "======================================================="
