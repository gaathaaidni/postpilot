#!/bin/bash
# PostPilot Web Server Production Startup Script
# Usage: ./run-production.sh [workers] [port] [host]
# Default host is 127.0.0.1 for security behind reverse proxy (Nginx)

WORKERS=${1:-4}
PORT=${2:-5000}
HOST=${3:-127.0.0.1}

echo "Starting PostPilot (Production Mode)"
echo "Host: $HOST | Port: $PORT | Workers: $WORKERS"

export APP_ENV=production
exec gunicorn \
    --workers $WORKERS \
    --worker-class sync \
    --bind $HOST:$PORT \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
