#!/bin/bash
# ==============================================================================
# PostPilot — Termux Startup Script
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 1. Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 2. Acquire Android Termux WakeLock to prevent OS process freezing
if command -v termux-wake-lock &> /dev/null; then
    termux-wake-lock
    echo "🔒 [Termux] WakeLock acquired (background process execution protected)"
fi

# 3. Environment defaults
export APP_ENV=termux
export FLASK_APP=app:app

echo "🚀 Starting PostPilot Application Server on http://127.0.0.1:5000..."
echo "👉 Open your mobile browser and navigate to: http://127.0.0.1:5000"
echo "👉 Press Ctrl+C or run ./stop-termux.sh to halt."

python app.py
