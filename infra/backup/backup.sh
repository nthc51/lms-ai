#!/bin/sh
# Một lần backup: dump Postgres (định dạng custom, nén sẵn) và nén dữ liệu MinIO. Giữ BACKUP_KEEP_DAYS ngày.
set -eu
: "${BACKUP_KEEP_DAYS:=7}"
ts=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /backups

# Ghi ra file .tmp rồi mới đổi tên: backup bị ngắt giữa chừng không để lại file "trông như hợp lệ"
pg_dump -Fc -f "/backups/db-$ts.dump.tmp"
mv "/backups/db-$ts.dump.tmp" "/backups/db-$ts.dump"

if [ -d /minio-data ]; then
  tar -czf "/backups/files-$ts.tar.gz.tmp" -C /minio-data .
  mv "/backups/files-$ts.tar.gz.tmp" "/backups/files-$ts.tar.gz"
fi

find /backups -name 'db-*.dump' -mtime +"$BACKUP_KEEP_DAYS" -delete
find /backups -name 'files-*.tar.gz' -mtime +"$BACKUP_KEEP_DAYS" -delete
echo "[backup] $ts xong: db $(du -h "/backups/db-$ts.dump" | cut -f1)"
