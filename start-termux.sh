#!/bin/bash
# ==============================================================================
# PostPilot — Termux Startup Script
# ==============================================================================
# Starts the PostPilot web dashboard (app.py) and the background scheduler
# worker (worker.py) with verified PID tracking, duplicate prevention, and WakeLock.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

mkdir -p data logs

APP_PID_FILE="data/app.pid"
WORKER_PID_FILE="data/worker.pid"

# Process liveness check helper (Linux / Termux + portable fallback)
is_pid_alive() {
    local pid="$1"
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    if command -v python &>/dev/null; then
        if python -c "import os, sys; os.kill(int(sys.argv[1]), 0)" "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Process termination helper (Linux / Termux + portable fallback)
kill_pid() {
    local pid="$1"
    local sig="${2:-}"
    if [ -n "$sig" ]; then
        kill "$sig" "$pid" 2>/dev/null || true
    else
        kill "$pid" 2>/dev/null || true
    fi
    if command -v taskkill &>/dev/null; then
        taskkill //F //PID "$pid" &>/dev/null || true
    elif command -v python &>/dev/null; then
        python -c "import os, signal, sys; os.kill(int(sys.argv[1]), signal.SIGTERM)" "$pid" 2>/dev/null || true
    fi
}

# 1. Process ownership validation helper
verify_process_ownership() {
    local raw_pid="$1"
    local expected_script="$2"
    local pid
    pid=$(echo "$raw_pid" | tr -dc '0-9')

    if [ -z "$pid" ]; then
        return 1
    fi

    # Verify process is actively running
    if ! is_pid_alive "$pid"; then
        return 1
    fi

    local cmdline=""
    local proc_cwd=""

    if [ -f "/proc/$pid/cmdline" ]; then
        cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    fi

    if [ -z "$cmdline" ] && command -v ps &> /dev/null; then
        cmdline=$(ps -p "$pid" -o args= 2>/dev/null || ps -o args= -p "$pid" 2>/dev/null || true)
    fi

    # If cmdline is undetermined or doesn't match, run Python inspection fallback
    if [ -z "$cmdline" ] || [[ "$cmdline" != *"python"* ]] || [[ "$cmdline" != *"$expected_script"* ]]; then
        if command -v python &> /dev/null; then
            local py_match
            py_match=$(python -c "
import sys, os
pid = sys.argv[1]
expected = sys.argv[2]
repo_dir = os.path.abspath(sys.argv[3]).lower()
cmd_file = f'/proc/{pid}/cmdline'
if os.path.exists(cmd_file):
    try:
        with open(cmd_file, 'rb') as f:
            cmd = f.read().decode('utf-8', errors='ignore').replace('\x00', ' ').lower()
        cwd = os.path.realpath(f'/proc/{pid}/cwd').lower() if os.path.exists(f'/proc/{pid}/cwd') else ''
        if 'python' in cmd and expected.lower() in cmd and (repo_dir in cmd or cwd == repo_dir or cwd.startswith(repo_dir + os.sep)):
            print('1')
            sys.exit(0)
    except Exception:
        pass
if sys.platform == 'win32':
    try:
        import subprocess
        cmd = subprocess.check_output(f'wmic process where ProcessId={pid} get CommandLine', shell=True, text=True, timeout=3).lower()
        if 'python' in cmd and expected.lower() in cmd:
            print('1')
            sys.exit(0)
    except Exception:
        pass
print('0')
" "$pid" "$expected_script" "$DIR" 2>/dev/null || echo "0")
            if [ "$py_match" = "1" ]; then
                return 0
            fi
        fi
        return 1
    fi

    # Verify repository association
    if [[ "$cmdline" == *"$DIR"* ]]; then
        return 0
    fi

    if [ -e "/proc/$pid/cwd" ]; then
        proc_cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || readlink "/proc/$pid/cwd" 2>/dev/null || true)
        if [ -n "$proc_cwd" ] && { [ "$proc_cwd" = "$DIR" ] || [[ "$proc_cwd" == "$DIR/"* ]]; }; then
            return 0
        fi
        return 1
    fi

    # Environments without /proc/$pid/cwd (such as Windows developer machines)
    local sys_uname
    sys_uname=$(uname -s 2>/dev/null || true)
    if [[ "$sys_uname" =~ ^(MINGW|MSYS|CYGWIN) ]]; then
        if [[ "$cmdline" == *"python"* ]] && [[ "$cmdline" == *"$expected_script"* ]]; then
            return 0
        fi
    fi

    return 1
}

# 2. Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 3. Check if PostPilot web server is already running (with process ownership validation)
if [ -f "$APP_PID_FILE" ]; then
    EXISTING_APP_PID=$(cat "$APP_PID_FILE" 2>/dev/null | tr -dc '0-9' || true)
    if [ -n "$EXISTING_APP_PID" ]; then
        if verify_process_ownership "$EXISTING_APP_PID" "app.py"; then
            echo "⚠️ PostPilot web server is already running (PID: $EXISTING_APP_PID)."
            echo "👉 Access in browser: http://127.0.0.1:5000"
            echo "👉 To stop it, run: ./stop-termux.sh"
            exit 0
        else
            echo "ℹ️ Stale or unowned app PID file detected (PID: $EXISTING_APP_PID); safely removing stale PID file."
            rm -f "$APP_PID_FILE"
        fi
    else
        rm -f "$APP_PID_FILE"
    fi
fi

# 4. Acquire Android Termux WakeLock to prevent CPU sleep suspension
if command -v termux-wake-lock &> /dev/null; then
    termux-wake-lock
    echo "🔒 [Termux] WakeLock acquired (protects background execution from CPU sleep)."
    echo "   Note: Android OS or OEM battery management may still terminate background apps"
    echo "   if RAM is low or if Termux battery optimization is not set to 'Unrestricted'."
fi

# 5. Environment defaults
export APP_ENV=termux
export FLASK_APP=app:app

# 6. Start background worker (if not already running)
START_WORKER=${START_WORKER:-1}
if [ "$START_WORKER" = "1" ]; then
    WORKER_RUNNING=0
    if [ -f "$WORKER_PID_FILE" ]; then
        EXISTING_WORKER_PID=$(cat "$WORKER_PID_FILE" 2>/dev/null | tr -dc '0-9' || true)
        if [ -n "$EXISTING_WORKER_PID" ]; then
            if verify_process_ownership "$EXISTING_WORKER_PID" "worker.py"; then
                echo "⚙️ [Worker] Background scheduler worker already running (PID: $EXISTING_WORKER_PID)."
                WORKER_RUNNING=1
            else
                echo "ℹ️ [Worker] Stale or unowned worker PID file detected (PID: $EXISTING_WORKER_PID); safely removing stale PID file."
                rm -f "$WORKER_PID_FILE"
            fi
        else
            rm -f "$WORKER_PID_FILE"
        fi
    fi

    if [ "$WORKER_RUNNING" = "0" ]; then
        python worker.py >> logs/worker.log 2>&1 &
        WORKER_PID=$!
        echo $WORKER_PID > "$WORKER_PID_FILE"
        echo "⚙️ [Worker] Background scheduler worker started (PID: $WORKER_PID, log: logs/worker.log)"
    fi
else
    echo "ℹ️ [Worker] Background scheduler disabled by START_WORKER=0 environment setting."
fi

# 7. Cleanup handler for graceful shutdown on Ctrl+C or termination
cleanup() {
    echo ""
    echo "🛑 Halting PostPilot..."
    if [ -f "$APP_PID_FILE" ]; then
        PID=$(cat "$APP_PID_FILE" 2>/dev/null | tr -dc '0-9' || true)
        if [ -n "$PID" ] && verify_process_ownership "$PID" "app.py"; then
            kill_pid "$PID"
        fi
        rm -f "$APP_PID_FILE"
    fi

    if [ -f "$WORKER_PID_FILE" ]; then
        PID=$(cat "$WORKER_PID_FILE" 2>/dev/null | tr -dc '0-9' || true)
        if [ -n "$PID" ] && verify_process_ownership "$PID" "worker.py"; then
            kill_pid "$PID"
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
