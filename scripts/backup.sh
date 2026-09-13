#!/usr/bin/env bash
# ReMuse 溯游每日备份：pg_dump → ./backups，保留最近 14 份。
# 用法：bash scripts/backup.sh   （建议加入系统计划任务，每日执行）
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups}"
KEEP="${KEEP:-14}"
PG_USER="${POSTGRES_USER:-flash}"
PG_DB="${POSTGRES_DB:-flash}"

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/flash-$(date +%Y%m%d-%H%M%S).sql.gz"

docker compose exec -T db pg_dump -U "$PG_USER" "$PG_DB" | gzip > "$FILE"

# 轮转：只保留最近 KEEP 份
ls -1t "$BACKUP_DIR"/flash-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "backup written: $FILE ($(du -h "$FILE" | cut -f1))"
