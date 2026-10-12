#!/usr/bin/env bash
# Deploy đúng một commit: ./infra/deploy/deploy.sh <git-sha>
# Nếu API hoặc web không sẵn sàng trong khoảng 2 phút → rollback về commit chạy tốt gần nhất rồi báo lỗi.
#
# Toàn bộ logic nằm trong main(): bash đọc hết hàm trước khi chạy, nên việc `git checkout` đổi chính
# file này giữa chừng không làm hỏng lần chạy đang diễn ra.
#
# Lưu ý: rollback chỉ quay lại code, KHÔNG hạ migration. Migration phải tương thích ngược
# (chỉ thêm cột hoặc bảng; xóa và đổi tên thì làm ở một lần deploy sau).
set -euo pipefail

main() {
  local sha="${1:?Cần git sha}"
  cd "$(dirname "$0")/../.."
  mkdir -p .deploy
  local last_good_file=.deploy/last_good_sha
  local prev
  prev=$(cat "$last_good_file" 2>/dev/null || true)

  echo "==> Deploy $sha (trước đó: ${prev:-chưa có})"
  git fetch --quiet origin
  git checkout --quiet --detach "$sha"
  ./infra/prod.sh up -d --build --remove-orphans

  if wait_ready; then
    echo "$sha" > "$last_good_file"
    docker image prune -f >/dev/null
    echo "==> OK: $sha đang chạy"
    return 0
  fi

  echo "==> $sha không sẵn sàng sau 2 phút (API /ready hoặc web), rollback về ${prev:-<không có>}" >&2
  if [ -n "$prev" ]; then
    git checkout --quiet --detach "$prev"
    ./infra/prod.sh up -d --build --remove-orphans
    wait_ready || echo "==> CẢNH BÁO: bản rollback cũng không sẵn sàng, cần xử lý tay" >&2
  fi
  return 1
}

wait_ready() {
  for _ in $(seq 1 40); do
    if ./infra/prod.sh exec -T api python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=3).status == 200 else 1)" \
      >/dev/null 2>&1 \
      && ./infra/prod.sh exec -T web wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  return 1
}

main "$@"
