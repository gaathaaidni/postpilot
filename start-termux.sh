#!/bin/bash
# ==============================================================================
# PostPilot — Termux Startup Script
# ==============================================================================
# Starts the PostPilot web dashboard (app.py) and the background scheduler
# worker (worker.py) with PID tracking, duplicate prevention, and WakeLock.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

mkdir -p data logs

APP_PID_FILE="data/app.pid"
WORKER_PID_FILE="data/worker.pid"

# 1. Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 2. Check if PostPilot web server is already running to prevent duplicate instances
if [ -f "$APP_PID_FILE" ]; then
    EXISTING_APP_PID=$(cat "$APP_PID_FILE" 2>/dev/null || true)
    if [ -n "$EXISTING_APP_PID" ] && kill -0 "$EXISTING_APP_PID" 2>/dev/null; then
        echo "⚠️ PostPilot web server is already running (PID: $EXISTING_APP_PID)."
        echo "👉 Access in browser: http://127.0.0.1:5000"
        echo "👉 To stop it, run: ./stop-termux.sh"
        exit 0
    fi
    rm -f "$APP_PID_FILE"
fi

# 3. Acquire Android Termux WakeLock to prevent CPU sleep suspension
if command -v termux-wake-lock &> /dev/null; then
    termux-wake-lock
    echo "🔒 [Termux] WakeLock acquired (protects background execution from CPU sleep)."
    echo "   Note: Android OS or OEM battery management may still terminate background apps"
    echo "   if RAM is low or if Termux battery optimization is not set to 'Unrestricted'."
fi

# 4. Environment defaults
export APP_ENV=termux
export FLASK_APP=app:app

# 5. Start background worker (if not already running)
# The worker daemon is REQUIRED for processing scheduled calendar posts and automated intervals.
START_WORKER=${START_WORKER:-1}
if [ "$START_WORKER" = "1" ]; then
    WORKER_RUNNING=0
    if [ -f "$WORKER_PID_FILE" ]; then
        EXISTING_WORKER_PID=$(cat "$WORKER_PID_FILE" 2>/dev/null || true)
        if [ -n "$EXISTING_WORKER_PID" ] && kill -0 "$EXISTING_WORKER_PID" 2>/dev/null; then
            echo "⚙️ [Worker] Background scheduler worker already running (PID: $EXISTING_WORKER_PID)."
            WORKER_RUNNING=1
        fi
    fi

    if [ "$WORKER_RUNNING" = "0" ]; then
        rm -f "$WORKER_PID_FILE"
        python worker.py >> logs/worker.log 2>&1 &
        WORKER_PID=$!
        echo $WORKER_PID > "$WORKER_PID_FILE"
        echo "⚙️ [Worker] Background scheduler worker started (PID: $WORKER_PID, log: logs/worker.log)"
    fi
else
    echo "ℹ️ [Worker] Background scheduler disabled by START_WORKER=0 environment setting."
fi

# 6. Cleanup handler for graceful shutdown on Ctrl+C or termination
cleanup() {
    echo ""
    echo "🛑 Halting PostPilot..."
    if [ -f "$APP_PID_FILE" ]; then
        PID=$(cat "$APP_PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null || true
        fi
        rm -f "$APP_PID_FILE"
    fi

    if [ -f "$WORKER_PID_FILE" ]; then
        PID=$(cat "$WORKER_PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null || true
        fi
        rm -f "$WORKER_PID_FILE"
    fi

    if command -v termux-wake-unlock &> /dev/null; then
        termux-wake-unlock
        echo "🔓 [Termux] WakeLock released"
    fi
    echo "✅ PostPilot halted cleanly."
    exit 0
}

trap cleanup INT TERM

echo "🚀 Starting PostPilot Application Server on http://127.0.0.1:5000..."
echo "👉 Open your mobile browser and navigate to: http://127.0.0.1:5000"
echo "👉 Press Ctrl+C or run ./stop-termux.sh from another session to halt."

# Start web app and track PID
python app.py &
APP_PID=$!
echo $APP_PID > "$APP_PID_FILE"

# Wait for web app process
wait $APP_PID 2>/dev/null || true
cleanup
