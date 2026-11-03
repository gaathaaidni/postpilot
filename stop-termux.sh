#!/bin/bash
# ==============================================================================
# PostPilot — Termux Shutdown Script
# ==============================================================================

echo "🛑 Stopping PostPilot processes..."

# Terminate running app and worker processes
pkill -f "python app.py" || true
pkill -f "python worker.py" || true

# Release WakeLock
if command -v termux-wake-unlock &> /dev/null; then
    termux-wake-unlock
    echo "🔓 [Termux] WakeLock released"
fi

echo "✅ PostPilot halted cleanly."
