#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="/root/postpilot/backups"
OFFSITE_DIR="/root/backups/postpilot"
mkdir -p "$BACKUP_DIR" "$OFFSITE_DIR"
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/posts_${TS}.db"
OFFSITE_FILE="${OFFSITE_DIR}/posts_${TS}.db"

python3 -c "
import sqlite3
src = sqlite3.connect('/root/postpilot/data/posts.db')
dst = sqlite3.connect('${BACKUP_FILE}')
src.backup(dst)
dst.close()
src.close()
"
cp "${BACKUP_FILE}" "${OFFSITE_FILE}"
chmod 600 "${BACKUP_FILE}" "${OFFSITE_FILE}"

# Retain 30 days of backups
find "${BACKUP_DIR}" -name "posts_*.db" -mtime +30 -delete 2>/dev/null || true
find "${OFFSITE_DIR}" -name "posts_*.db" -mtime +30 -delete 2>/dev/null || true
