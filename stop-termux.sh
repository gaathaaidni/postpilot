#!/bin/bash
# ==============================================================================
# PostPilot — Termux Shutdown Script
# ==============================================================================
# Stops ONLY PostPilot application and worker processes using PID files and
# repository-scoped path matching. Never terminates unrelated Python processes.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "🛑 Stopping PostPilot processes..."

stop_pid() {
    local pid_file="$1"
    local proc_name="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "   Stopping $proc_name (PID $pid)..."
            kill "$pid" 2>/dev/null || true
            for i in 1 2 3; do
                if kill -0 "$pid" 2>/dev/null; then
                    sleep 1
                else
                    break
                fi
            done
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
            echo "   ✅ $proc_name stopped."
        fi
        rm -f "$pid_file"
    fi
}

# 1. Stop application server via PID file
stop_pid "data/app.pid" "web server"

# 2. Stop scheduler worker via PID file
stop_pid "data/worker.pid" "background worker"

# 3. Scoped fallback: only kill processes whose command line explicitly references this repository's scripts
if command -v pkill &> /dev/null; then
    pkill -f "python.*$DIR/app.py" 2>/dev/null || true
    pkill -f "python.*$DIR/worker.py" 2>/dev/null || true
fi

# 4. Release Android WakeLock
if command -v termux-wake-unlock &> /dev/null; then
    termux-wake-unlock
    echo "🔓 [Termux] WakeLock released"
fi

echo "✅ PostPilot halted cleanly."
