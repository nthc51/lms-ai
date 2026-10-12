#!/bin/sh
# Chạy backup ngay khi khởi động, sau đó cứ BACKUP_INTERVAL_S giây một lần.
set -eu
: "${BACKUP_INTERVAL_S:=86400}"
while true; do
  /bin/sh /scripts/backup.sh || echo "[backup] LỖI: lần backup này thất bại" >&2
  sleep "$BACKUP_INTERVAL_S"
done
