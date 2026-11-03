#!/bin/bash
# ==============================================================================
# PostPilot — Termux Shutdown Script
# ==============================================================================
# Stops ONLY PostPilot application and worker processes using verified PID
# ownership and repository-scoped path matching. Never terminates unrelated
# Python or system processes.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "🛑 Stopping PostPilot processes..."

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

stop_pid() {
    local pid_file="$1"
    local expected_script="$2"
    local proc_name="$3"

    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null | tr -dc '0-9' || true)
        if [ -n "$pid" ]; then
            if verify_process_ownership "$pid" "$expected_script"; then
                echo "   Stopping $proc_name (PID $pid)..."
                kill_pid "$pid"
                for i in 1 2 3; do
                    if is_pid_alive "$pid"; then
                        sleep 1
                    else
                        break
                    fi
                done
                if is_pid_alive "$pid"; then
                    kill_pid "$pid" -9
                fi
                echo "   ✅ $proc_name stopped."
            else
                echo "   ℹ️ PID $pid in $pid_file does not belong to PostPilot $proc_name (stale or foreign process); preserving process and removing stale PID file."
            fi
        fi
        rm -f "$pid_file"
    fi
}

# 1. Stop application server via verified PID file
stop_pid "data/app.pid" "app.py" "web server"

# 2. Stop scheduler worker via verified PID file
stop_pid "data/worker.pid" "worker.py" "background worker"

# 3. Scoped fallback: check for untracked processes belonging strictly to this repository
if command -v pgrep &> /dev/null; then
    for p in $(pgrep -f "python.*app\.py" 2>/dev/null || true); do
        if verify_process_ownership "$p" "app.py"; then
            echo "   Stopping untracked PostPilot web server (PID $p)..."
            kill_pid "$p"
        fi
    done
    for p in $(pgrep -f "python.*worker\.py" 2>/dev/null || true); do
        if verify_process_ownership "$p" "worker.py"; then
            echo "   Stopping untracked PostPilot background worker (PID $p)..."
            kill_pid "$p"
        fi
    done
fi

# 4. Release Android WakeLock
if command -v termux-wake-unlock &> /dev/null; then
    termux-wake-unlock
    echo "🔓 [Termux] WakeLock released"
fi

echo "✅ PostPilot halted cleanly."
