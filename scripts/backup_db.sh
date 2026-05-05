#!/usr/bin/env bash
# FinForge DB Backup Script
# Usage:
#   ./backup_db.sh                    # reads DATABASE_URL from env
#   ./backup_db.sh <database_url>     # accepts URL as first argument
#
# Crontab: 0 4 * * * /opt/finforge/scripts/backup_db.sh >> /var/log/finforge_backup.log 2>&1

set -euo pipefail

BACKUP_DIR="/backups"
KEEP_COUNT=30
TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/finforge_${TIMESTAMP}.sql.gz"

DB_URL="${1:-${DATABASE_URL:-}}"

if [[ -z "$DB_URL" ]]; then
    echo "$(date -Iseconds) ERROR: DATABASE_URL not set and no argument provided."
    exit 1
fi

# Parse: postgresql://user:password@host:port/dbname
WITHOUT_SCHEME="${DB_URL#*://}"
USERPASS="${WITHOUT_SCHEME%%@*}"
PGUSER="${USERPASS%%:*}"
PGPASSWORD="${USERPASS#*:}"
HOSTPORTDB="${WITHOUT_SCHEME#*@}"
HOSTPORT="${HOSTPORTDB%%/*}"
PGHOST="${HOSTPORT%%:*}"
PGPORT="${HOSTPORT#*:}"
PGDATABASE="${HOSTPORTDB#*/}"
PGDATABASE="${PGDATABASE%%\?*}"

export PGPASSWORD

mkdir -p "$BACKUP_DIR"

echo "$(date -Iseconds) INFO: Starting backup of '${PGDATABASE}' → ${BACKUP_FILE}"

if pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
    --no-owner --no-acl | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "$(date -Iseconds) INFO: Backup succeeded — ${BACKUP_FILE} (${SIZE})"
else
    echo "$(date -Iseconds) ERROR: pg_dump failed for '${PGDATABASE}'"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Prune old backups
BACKUP_COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -name 'finforge_*.sql.gz' -type f | wc -l | tr -d ' ')

if [[ "$BACKUP_COUNT" -gt "$KEEP_COUNT" ]]; then
    DELETE_COUNT=$((BACKUP_COUNT - KEEP_COUNT))
    echo "$(date -Iseconds) INFO: Pruning ${DELETE_COUNT} old backup(s) (keeping ${KEEP_COUNT})"
    ls -1t "$BACKUP_DIR"/finforge_*.sql.gz | tail -n "$DELETE_COUNT" | xargs rm -f
fi

echo "$(date -Iseconds) INFO: Backup complete. ${BACKUP_COUNT} total backups in ${BACKUP_DIR}."
