#!/bin/bash

# PostPilot Flask App - Production Run Script
# This script runs the app using Gunicorn (production WSGI server)
# Usage: ./run-production.sh [workers] [port]

WORKERS=${1:-4}
PORT=${2:-5000}

echo "🚀 PostPilot Flask (Production Mode)"
echo "===================================="
echo ""
echo "Configuration:"
echo "  Workers: $WORKERS"
echo "  Port: $PORT"
echo ""

# Install production requirements
pip install -r requirements.txt -q

# Run with Gunicorn
echo "Starting server with $WORKERS workers..."
gunicorn \
    --workers $WORKERS \
    --worker-class sync \
    --bind 0.0.0.0:$PORT \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
