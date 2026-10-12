#!/bin/sh
# Khôi phục bản backup (mặc định là bản mới nhất) vào DB tạm, so số dòng các bảng chính, in thời gian khôi phục.
# Dùng: ./infra/prod.sh exec backup sh /scripts/restore-check.sh [/backups/db-....dump]
# Nên chạy lúc không có ai dùng hệ thống, nếu không số dòng có thể lệch do dữ liệu mới ghi sau lúc dump.
set -eu
file="${1:-$(ls -1t /backups/db-*.dump | head -n 1)}"
echo "Khôi phục từ: $file"

dropdb --if-exists lms_restore_check
createdb lms_restore_check
start=$(date +%s)
pg_restore --no-owner --exit-on-error -d lms_restore_check "$file"
end=$(date +%s)

status=0
for t in users courses lessons sources chunks; do
  a=$(psql -tA -d lms -c "SELECT count(*) FROM $t")
  b=$(psql -tA -d lms_restore_check -c "SELECT count(*) FROM $t")
  echo "  $t: gốc=$a  khôi_phục=$b"
  [ "$a" = "$b" ] || status=1
done
dropdb lms_restore_check

echo "Thời gian khôi phục: $((end - start)) giây"
[ "$status" -eq 0 ] && echo "KẾT QUẢ: khớp" || { echo "KẾT QUẢ: LỆCH số dòng" >&2; exit 1; }
