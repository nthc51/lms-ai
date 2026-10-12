#!/usr/bin/env bash
# Kiểm tra deploy.sh chọn đúng service cần cập nhật và rollback đúng, không cần Docker hay VPS.
# Dựng một repo git tạm, thay infra/prod.sh bằng bản giả ghi lại lệnh, rồi deploy từng loại thay đổi.
# Chạy: bash infra/deploy/test_deploy.sh   (Git Bash trên Windows cũng chạy được)
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/deploy.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
printf '#!/bin/sh\nexit 0\n' > "$T/bin/sleep"   # bỏ thời gian chờ 3 giây giữa các lần kiểm
printf '#!/bin/sh\nexit 0\n' > "$T/bin/docker"  # docker image prune
chmod +x "$T/bin/sleep" "$T/bin/docker"

git init -q --bare "$T/origin.git"
git clone -q "$T/origin.git" "$T/work" 2>/dev/null
cd "$T/work"
git config user.email test@example.com
git config user.name test
mkdir -p infra/deploy backend frontend docs
cp "$SRC" infra/deploy/deploy.sh
cat > infra/prod.sh <<'STUB'
#!/usr/bin/env bash
# Bản giả: "exec" (kiểm tra sẵn sàng) thành công trừ khi có file FAIL; lệnh khác thì ghi lại
cd "$(dirname "$0")/.."
if [ "$1" = exec ]; then
  [ -f ../FAIL ] && exit 1
  exit 0
fi
echo "$*" >> ../calls.log
STUB
chmod +x infra/prod.sh infra/deploy/deploy.sh
echo a > backend/a.py; echo b > frontend/b.ts; echo d > docs/d.md; echo c > docker-compose.prod.yml
echo ".deploy/" > .gitignore
git add -A && git commit -qm init && git push -q origin HEAD:main 2>/dev/null

commit() { echo "$RANDOM" >> "$1"; git add -A; git commit -qm "$1"; git push -q origin HEAD:main 2>/dev/null; git rev-parse HEAD; }
fails=0
check() {  # check <tên> <sha> <mã thoát mong đợi> <các lệnh prod.sh mong đợi, nối bằng |>
  : > ../calls.log
  local code=0
  PATH="$T/bin:$PATH" ./infra/deploy/deploy.sh "$2" > ../out.log 2>&1 || code=$?
  local got
  got=$(paste -sd'|' ../calls.log)
  if [ "$code" = "$3" ] && [ "$got" = "$4" ]; then
    echo "OK   $1"
  else
    echo "FAIL $1: thoát $code (mong $3), lệnh [$got] (mong [$4])"
    sed 's/^/     /' ../out.log
    fails=$((fails + 1))
  fi
}

ALL="up -d --build --remove-orphans"
check "lần đầu: cả stack" "$(git rev-parse HEAD)" 0 "$ALL"
check "đổi backend: api + worker" "$(commit backend/a.py)" 0 "up -d --build --no-deps api worker"
check "đổi frontend: web" "$(commit frontend/b.ts)" 0 "up -d --build --no-deps web"
check "chỉ tài liệu: không khởi động lại" "$(commit docs/d.md)" 0 ""
check "đổi compose: cả stack" "$(commit docker-compose.prod.yml)" 0 "$ALL"
good=$(cat .deploy/last_good_sha)
bad=$(commit backend/a.py)
touch ../FAIL
check "backend lỗi: rollback api + worker" "$bad" 1 "up -d --build --no-deps api worker|up -d --build --no-deps api worker"
rm ../FAIL
if [ "$(cat .deploy/last_good_sha)" = "$good" ]; then echo "OK   rollback giữ nguyên commit chạy tốt"; else echo "FAIL last_good_sha bị đổi"; fails=$((fails + 1)); fi

if [ "$fails" -ne 0 ]; then
  echo "$fails trường hợp sai" >&2
  exit 1
fi
echo "Tất cả đều đúng"
