# Ranh giới module và CI/CD theo từng phần: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Mục tiêu:** sửa / nâng cấp phần nào thì chỉ đụng phần đó:

- Backend và frontend có **ranh giới module được CI kiểm tra**: phần nền không phụ thuộc phần tính năng, tính năng này không kéo theo tính năng kia. Lỡ tạo phụ thuộc sai thì CI báo đỏ ngay.
- **CI chạy theo thư mục**: chỉ sửa frontend thì không chạy test backend (và ngược lại); chỉ sửa tài liệu thì gần như không chạy gì.
- **Deploy theo phần**: chỉ build lại và khởi động lại service bị đổi (`api` + `worker`, hoặc `web`, hoặc cả stack khi đổi hạ tầng). Logic này có test chạy được trên máy và trong CI.
- Tài liệu `docs/architecture/modules.md`: bản đồ các phần, bảng DB, test, và "sửa phần X thì chạy gì, deploy gì".

**Không tách microservice.** Mọi phần dùng chung một database và transaction (ví dụ đăng ký tài khoản và ghi email vào hộp thư đi phải cùng một transaction). Kiến trúc "một khối chia module" giữ được sự độc lập khi bảo trì mà không thêm chi phí mạng, deploy và đồng bộ dữ liệu.

**Mã trong plan đã được chạy thử** trên bản đã xong plan admin, plan AI Studio và tầng S Task 1–11:

- Backend: `lint-imports` **5 hợp đồng đều KEPT**. Thử cố ý thêm `from app.modules.studio.models import Note` vào `courses/service.py` → **BROKEN** như mong đợi.
- Frontend: `eslint`, `tsc` sạch; **106 unit test pass**; **77 E2E pass + 1 bỏ qua có chủ ý** (số sau plan AI Studio bản 08/10); `next build` sạch. Thử cố ý import component admin từ studio, import studio từ `lib`, import admin từ `components/ui` → cả 3 đều báo lỗi.
- `ci.yml`: `actionlint` sạch. Bước kiểm `docker-compose.prod.yml` đã chạy thử.
- `deploy.sh`: `shellcheck` sạch; `test_deploy.sh` **7/7 trường hợp đúng**. Thử cố ý sửa sai cách chọn service → test báo `FAIL`.
- Riêng bước kiểm Caddyfile trong CI (`docker run caddy:2-alpine caddy validate`) chưa chạy được trên máy thử (không tải được image), nhưng cùng lệnh `caddy validate` với cùng Caddyfile đã chạy và báo `Valid configuration`.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit.

---

## 0. Bối cảnh

### 0.1 Điều kiện bắt đầu

- Đã xong: plan admin, plan AI Studio (Task 1–11), **plan tầng S Task 1–11**. Plan này thay toàn bộ `.github/workflows/ci.yml` và `infra/deploy/deploy.sh` ở dạng **sau** tầng S (đã có job `audit`, bước `gen_erd --check`, `deploy.sh` có rollback).
- Task 6 cần VPS và CD đã chạy (tầng S Task 12). Chưa có VPS thì làm Task 1–5 trước, Task 6 làm sau.
- Không commit `.env`, `.env.prod`. Commit không thêm dòng `Co-Authored-By` hay `Claude-Session`.

### 0.2 Hiện trạng phụ thuộc (đã đo trên code)

Backend đã chia module tốt; các phụ thuộc đi một chiều (tính năng → nền). Hai ngoại lệ được ghi nhận, không sửa:

- `courses.service` **đọc** bảng `quiz` và `tutor` để chặn xóa khóa đã có học viên làm bài / hỏi AI.
- `courses` và `enrollment` gọi qua lại (cùng là phần nền).

Frontend có 2 component dùng chung nhưng đang nằm trong thư mục `admin`, khiến Studio và trang giảng viên phải import từ khu quản trị:

| File | Dùng ở | Chuyển tới |
|---|---|---|
| `components/admin/filter-tabs.tsx` | admin, **studio** | `components/ui/filter-tabs.tsx` |
| `components/admin/feedback-list.tsx` (câu trả lời AI Tutor bị 👎) | admin, **teach** | `components/tutor/feedback-list.tsx` |

---

## Task 1: Ranh giới module backend (`import-linter`)

**Files:**
- Create: `backend/.importlinter`
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (qua `uv add`)

- [ ] **Bước 1: Thêm thư viện** (trong `backend/`): `uv add --dev import-linter`

- [ ] **Bước 2: Hợp đồng** (`backend/.importlinter`)

```ini
# Ranh giới module của backend. Chạy: uv run lint-imports (CI chạy ở job lint).
# Phần NỀN (auth, courses, enrollment, materials, jobs, notify) không được phụ thuộc phần TÍNH NĂNG
# (tutor, quiz, studio, analytics, admin). Nhờ vậy sửa / bỏ một tính năng không kéo theo phần nền.
# Mỗi ngoại lệ phải ghi lý do; thêm ngoại lệ mới nghĩa là phải giải thích được vì sao.

[importlinter]
root_package = app
include_external_packages = False

[importlinter:contract:base-not-depend-on-features]
name = Phần nền không import phần tính năng
type = forbidden
source_modules =
    app.modules.auth
    app.modules.courses
    app.modules.enrollment
    app.modules.materials
    app.modules.jobs
    app.modules.notify
forbidden_modules =
    app.modules.tutor
    app.modules.quiz
    app.modules.studio
    app.modules.analytics
    app.modules.admin
ignore_imports =
    # Chặn xóa khóa / chương / bài khi học viên đã làm quiz hoặc hỏi AI Tutor: chỉ ĐỌC bảng, không gọi service
    app.modules.courses.service -> app.modules.quiz.models
    app.modules.courses.service -> app.modules.tutor.models

[importlinter:contract:notify-is-leaf]
name = notify (hộp thư đi email) không phụ thuộc module nào khác
type = forbidden
source_modules =
    app.modules.notify
forbidden_modules =
    app.modules.auth
    app.modules.courses
    app.modules.enrollment
    app.modules.materials
    app.modules.jobs

[importlinter:contract:tutor-quiz-independent]
name = AI Tutor và Quiz độc lập với nhau
type = independence
modules =
    app.modules.tutor
    app.modules.quiz
ignore_imports =
    # Cùng ngoại lệ chặn xóa ở trên (đường vòng qua courses.service, chỉ đọc bảng)
    app.modules.courses.service -> app.modules.quiz.models
    app.modules.courses.service -> app.modules.tutor.models

[importlinter:contract:core-and-ai-below-features]
name = core, lớp AI và ingestion không phụ thuộc phần tính năng
type = forbidden
source_modules =
    app.core
    app.ai
    app.ingestion
forbidden_modules =
    app.modules.tutor
    app.modules.quiz
    app.modules.studio
    app.modules.analytics
    app.modules.admin
    app.worker
    app.main

[importlinter:contract:modules-not-import-entrypoints]
name = Module không import điểm khởi động (main, worker)
type = forbidden
source_modules =
    app.modules
forbidden_modules =
    app.main
    app.worker
```

- [ ] **Bước 3: Chạy**: `uv run lint-imports`

Expected: 5 dòng `KEPT`, cuối cùng `Contracts: 5 kept, 0 broken.`

- [ ] **Bước 4: Thử vi phạm** (không commit): thêm dòng đầu `app/modules/courses/service.py`:

```python
from app.modules.studio.models import Note  # noqa
```

Chạy lại `uv run lint-imports` → `Phần nền không import phần tính năng BROKEN`, mã thoát khác 0. **Xóa dòng vừa thêm**, chạy lại → `5 kept`.

- [ ] **Bước 5: Commit**

```bash
git add backend/.importlinter backend/pyproject.toml backend/uv.lock
git commit -m "chore(api): enforce module boundaries with import-linter"
```

---

## Task 2: Ranh giới thư mục frontend

**Files:**
- Move: `frontend/src/components/admin/filter-tabs.tsx` → `frontend/src/components/ui/filter-tabs.tsx`
- Move: `frontend/src/components/admin/feedback-list.tsx` → `frontend/src/components/tutor/feedback-list.tsx`
- Modify: 5 file import hai component trên, `frontend/eslint.config.mjs`

- [ ] **Bước 1: Chuyển file** (ở gốc repo)

```bash
git mv frontend/src/components/admin/filter-tabs.tsx frontend/src/components/ui/filter-tabs.tsx
git mv frontend/src/components/admin/feedback-list.tsx frontend/src/components/tutor/feedback-list.tsx
```

- [ ] **Bước 2: Sửa import** (nội dung hai file giữ nguyên, chỉ đổi đường dẫn ở nơi dùng)

| File | Dòng cũ → dòng mới |
|---|---|
| `src/app/(main)/admin/users/page.tsx` | `@/components/admin/filter-tabs` → `@/components/ui/filter-tabs` |
| `src/app/(main)/admin/courses/page.tsx` | `@/components/admin/filter-tabs` → `@/components/ui/filter-tabs` |
| `src/components/studio/studio-panel.tsx` | `@/components/admin/filter-tabs` → `@/components/ui/filter-tabs` |
| `src/app/(main)/admin/feedback/page.tsx` | `@/components/admin/feedback-list` → `@/components/tutor/feedback-list` |
| `src/components/teach/course-analytics.tsx` | `@/components/admin/feedback-list` → `@/components/tutor/feedback-list` |

Kiểm tra không còn chỗ nào: `grep -rn "components/admin/filter-tabs\|components/admin/feedback-list" frontend/src frontend/e2e` → không in gì.

- [ ] **Bước 3: Luật ESLint** (`eslint.config.mjs`): chèn khối dưới đây vào trong `defineConfig([...])`, ngay **sau** `...nextTs,` và **trước** dòng `// Override default ignores of eslint-config-next.`

```js
  // Ranh giới thư mục: phần dùng chung không được phụ thuộc một tính năng cụ thể,
  // và component của khu quản trị chỉ dùng trong khu quản trị. Sửa / bỏ một tính năng không kéo theo phần khác.
  {
    files: ["src/lib/**", "src/components/ui/**", "src/components/app/**", "src/components/content/**"],
    ignores: ["src/**/*.test.ts", "src/**/*.test.tsx"], // test được dựng component thật để kiểm hook
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "@/components/*",
                "!@/components/ui",
                "!@/components/ui/**",
                "!@/components/app",
                "!@/components/app/**",
                "!@/components/content",
                "!@/components/content/**",
              ],
              message: "Phần dùng chung (lib, ui, app, content) không được import component của một tính năng.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/**"],
    // lib / ui / app / content đã bị chặn rộng hơn ở khối trên (khối sau sẽ ghi đè cùng rule nên phải loại ra)
    ignores: [
      "src/components/admin/**",
      "src/app/(main)/admin/**",
      "src/lib/**",
      "src/components/ui/**",
      "src/components/app/**",
      "src/components/content/**",
    ],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/components/admin", "@/components/admin/**"],
              message: "Component khu quản trị chỉ dùng trong khu quản trị. Thứ dùng chung thì chuyển sang components/ui hoặc thư mục của tính năng.",
            },
          ],
        },
      ],
    },
  },
```

Hai khối cùng dùng rule `no-restricted-imports`: với file khớp cả hai khối thì khối sau ghi đè khối trước. Vì vậy khối thứ hai phải loại `lib`, `ui`, `app`, `content` ra (khối thứ nhất đã chặn rộng hơn cho các thư mục đó).

- [ ] **Bước 4: Chạy** (trong `frontend/`)

```bash
npx eslint src e2e && npx tsc --noEmit && npx vitest run
```

Expected: sạch; 106 test pass.

- [ ] **Bước 5: Thử vi phạm** (không commit): thêm vào `src/components/studio/study-tabs.tsx` dòng `import { UserTable as _U } from "@/components/admin/user-table";`, và vào cuối `src/lib/utils.ts` dòng `export { StudyTabs as _x } from "@/components/studio/study-tabs";`. Chạy `npx eslint src` → 2 lỗi `no-restricted-imports`. **Trả lại hai file** (`git checkout -- src/components/studio/study-tabs.tsx src/lib/utils.ts`).

- [ ] **Bước 6:** `npx playwright test` → 77 passed, 1 skipped. Commit:

```bash
git add frontend && git commit -m "refactor(web): move shared filter tabs and tutor feedback list out of admin, enforce folder boundaries"
```

---

## Task 3: CI chạy theo thư mục

**Files:**
- Modify: `.github/workflows/ci.yml` (thay toàn bộ)

Job `changes` dùng `dorny/paths-filter` xem lần push đổi phần nào; job của phần không đổi bị **bỏ qua** (GitHub tính là xanh, nên workflow `Deploy` vẫn chạy và `deploy.sh` tự quyết không khởi động lại gì).

| Đổi | Job chạy |
|---|---|
| `backend/**` | `lint` (ruff, `lint-imports`, `gen_erd --check`), `test`, `docker` (image backend), `audit` (pip-audit) |
| `backend/app/**` | thêm `frontend` (kiểm kiểu TypeScript sinh từ OpenAPI còn khớp) |
| `frontend/**` | `frontend`, `docker` (image web), `audit` (npm audit) |
| `infra/**`, `docker-compose.prod.yml`, `.env.prod.example` | `infra` (shellcheck, test `deploy.sh`, kiểm compose, kiểm Caddyfile) |
| `ci.yml` | tất cả |
| chỉ `docs/`, `*.md` ở gốc | chỉ `changes` |

- [ ] **Bước 1: `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

defaults:
  run:
    working-directory: backend

jobs:
  # Xem lần push này đổi phần nào. Job của phần không đổi bị bỏ qua (skipped vẫn tính là xanh).
  changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
      frontend: ${{ steps.filter.outputs.frontend }}
      infra: ${{ steps.filter.outputs.infra }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            backend:
              - 'backend/**'
              - '.github/workflows/ci.yml'
            frontend:
              - 'frontend/**'
              # API đổi thì kiểu TypeScript sinh từ OpenAPI có thể lệch: chạy lại kiểm tra frontend
              - 'backend/app/**'
              - '.github/workflows/ci.yml'
            infra:
              - 'infra/**'
              - 'docker-compose.prod.yml'
              - '.env.prod.example'
              - '.github/workflows/ci.yml'

  lint:
    needs: changes
    if: needs.changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          version: "0.12.20"
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - name: Ranh giới module (backend/.importlinter)
        run: uv run lint-imports
      - run: uv run python -m scripts.gen_erd --check

  test:
    needs: changes
    if: needs.changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    services:
      db:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: lms
          POSTGRES_PASSWORD: lms
          # conftest chỉ cho chạy trên DB có đuôi _test
          POSTGRES_DB: lms_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U lms -d lms_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+asyncpg://lms:lms@127.0.0.1:5432/lms_test
      REDIS_URL: redis://127.0.0.1:6379/0
      PYTHONUTF8: "1"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          version: "0.12.20"
      - run: uv sync --frozen
      - run: uv run pytest -q

  frontend:
    needs: changes
    if: needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - uses: astral-sh/setup-uv@v6
        with:
          version: "0.12.20"
      - run: npm ci
      - name: Type API khớp với backend (quên chạy gen:api thì fail)
        run: npm run gen:api && git diff --exit-code -- openapi.json src/lib/api/schema.d.ts
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test
      - run: npx playwright install --with-deps chromium
      - run: npm run e2e
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-traces
          path: frontend/test-results
          retention-days: 7

  docker:
    needs: changes
    if: needs.changes.outputs.backend == 'true' || needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build backend image (không push)
        if: needs.changes.outputs.backend == 'true'
        uses: docker/build-push-action@v6
        with:
          context: backend
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Build frontend image (không push)
        if: needs.changes.outputs.frontend == 'true'
        uses: docker/build-push-action@v6
        with:
          context: frontend
          push: false
          build-args: API_ORIGIN=http://api:8000
          cache-from: type=gha,scope=web
          cache-to: type=gha,mode=max,scope=web

  audit:
    needs: changes
    if: needs.changes.outputs.backend == 'true' || needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        if: needs.changes.outputs.backend == 'true'
        with:
          version: "0.12.20"
      - name: Xuất danh sách thư viện production
        if: needs.changes.outputs.backend == 'true'
        run: uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt -o /tmp/req.txt
      - name: Quét lỗ hổng đã công bố (OSV/PyPI advisory)
        if: needs.changes.outputs.backend == 'true'
        run: uvx pip-audit -r /tmp/req.txt
      - name: Quét lỗ hổng thư viện frontend (chỉ thư viện chạy production, mức high trở lên)
        if: needs.changes.outputs.frontend == 'true'
        working-directory: frontend
        run: npm audit --omit=dev --audit-level=high

  infra:
    needs: changes
    if: needs.changes.outputs.infra == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: .
    steps:
      - uses: actions/checkout@v4
      - name: Kiểm tra script shell
        run: shellcheck -S warning infra/prod.sh infra/deploy/*.sh infra/backup/*.sh
      - name: deploy.sh chọn đúng service và rollback đúng
        run: bash infra/deploy/test_deploy.sh
      - name: docker-compose.prod.yml hợp lệ
        run: |
          cp .env.prod.example .env.prod
          sed -i 's/^\([A-Z_]*\)=$/\1=ci-dummy/' .env.prod
          docker compose -f docker-compose.prod.yml --env-file .env.prod config --quiet
      - name: Caddyfile hợp lệ
        run: >-
          docker run --rm -v "$PWD/infra/caddy/Caddyfile:/etc/caddy/Caddyfile:ro"
          -e APP_DOMAIN=localhost -e FILES_DOMAIN=files.localhost -e GRAFANA_DOMAIN=grafana.localhost
          -e ACME_EMAIL=ci@example.com caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

- [ ] **Bước 2: Kiểm cú pháp (tùy chọn):** nếu có Docker: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest` → không in lỗi.

- [ ] **Bước 3: Commit** (push ở Task 6)

```bash
git add .github/workflows/ci.yml && git commit -m "ci: run jobs only for the parts that changed"
```

---

## Task 4: Deploy theo phần

**Files:**
- Modify: `infra/deploy/deploy.sh` (thay toàn bộ)
- Create: `infra/deploy/test_deploy.sh`

`deploy.sh` so commit mới với commit đang chạy tốt (`.deploy/last_good_sha`):

| Đổi | Lệnh |
|---|---|
| Lần đầu (chưa có commit chạy tốt) | `up -d --build --remove-orphans` (cả stack) |
| `docker-compose.prod.yml` hoặc `infra/**` | cả stack |
| `backend/**` | `up -d --build --no-deps api worker` |
| `frontend/**` | `up -d --build --no-deps web` |
| cả hai | `… --no-deps api worker web` |
| còn lại (tài liệu, `.github/`) | không khởi động lại; ghi nhận commit là chạy tốt |

Rollback dùng **đúng danh sách service đó** ở commit cũ. Migration vẫn chạy trong lệnh khởi động `api` như trước.

- [ ] **Bước 1: `infra/deploy/deploy.sh`**

```bash
#!/usr/bin/env bash
# Deploy đúng một commit: ./infra/deploy/deploy.sh <git-sha>
# Chỉ build lại và khởi động lại phần bị đổi so với commit đang chạy tốt:
#   backend/**  → api, worker      frontend/** → web
#   docker-compose.prod.yml, infra/** → cả stack      chỉ tài liệu → không khởi động lại gì
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
  local services
  services=$(changed_services "$prev" "$sha")
  git checkout --quiet --detach "$sha"

  if [ -z "$services" ]; then
    echo "==> Chỉ đổi tài liệu / file không chạy: không khởi động lại service nào"
    echo "$sha" > "$last_good_file"
    return 0
  fi
  echo "==> Phần cần cập nhật: $services"
  apply "$services"

  if wait_ready; then
    echo "$sha" > "$last_good_file"
    docker image prune -f >/dev/null
    echo "==> OK: $sha đang chạy"
    return 0
  fi

  echo "==> $sha không sẵn sàng sau 2 phút (API /ready hoặc web), rollback về ${prev:-<không có>}" >&2
  if [ -n "$prev" ]; then
    git checkout --quiet --detach "$prev"
    apply "$services"
    wait_ready || echo "==> CẢNH BÁO: bản rollback cũng không sẵn sàng, cần xử lý tay" >&2
  fi
  return 1
}

# In ra "all", danh sách service (vd. "api worker web"), hoặc chuỗi rỗng nếu không cần khởi động lại gì.
changed_services() {
  local prev="$1" sha="$2"
  if [ -z "$prev" ]; then
    echo all
    return
  fi
  local files
  files=$(git diff --name-only "$prev" "$sha")
  if grep -qE '^(docker-compose\.prod\.yml|infra/)' <<<"$files"; then
    echo all
    return
  fi
  local out=""
  if grep -q '^backend/' <<<"$files"; then out="$out api worker"; fi
  if grep -q '^frontend/' <<<"$files"; then out="$out web"; fi
  echo "${out# }"
}

apply() {
  local services="$1"
  if [ "$services" = all ]; then
    ./infra/prod.sh up -d --build --remove-orphans
  else
    # --no-deps: không khởi động lại db, redis, minio... đang chạy ổn
    # shellcheck disable=SC2086
    ./infra/prod.sh up -d --build --no-deps $services
  fi
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
```

- [ ] **Bước 2: `infra/deploy/test_deploy.sh`**: dựng repo git tạm, thay `prod.sh` bằng bản giả ghi lại lệnh, deploy từng loại thay đổi.

```bash
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
```

- [ ] **Bước 3: Chạy** (Git Bash, ở gốc repo)

```bash
git update-index --chmod=+x infra/deploy/test_deploy.sh
bash infra/deploy/test_deploy.sh
```

Expected: 7 dòng `OK`, cuối cùng `Tất cả đều đúng`.

- [ ] **Bước 4: Thử làm sai** (không commit): trong `deploy.sh` đổi `out="$out web"` thành `out="$out api web"`, chạy lại → `FAIL đổi frontend: web …` và `1 trường hợp sai`. Trả lại: `git checkout -- infra/deploy/deploy.sh`.

- [ ] **Bước 5: Commit**

```bash
git add infra/deploy && git commit -m "feat(ops): deploy rebuilds only the services that changed, with a local test"
```

---

## Task 5: Tài liệu "các phần của hệ thống"

**Files:**
- Create: `docs/architecture/modules.md`
- Modify: `docs/architecture/README.md` (tầng S Task 15), `CLAUDE.md` ở gốc repo nếu có

- [ ] **Bước 1: `docs/architecture/modules.md`**: trước khi commit, **đối chiếu với code** (tên file test, tên bảng); chỗ nào lệch thì sửa theo code thật.

````markdown
# Các phần của hệ thống và cách sửa từng phần

Hệ thống là **một khối chia module** (modular monolith): một backend, một database, nhưng mỗi tính năng nằm trong thư mục riêng, có test riêng, và ranh giới giữa các phần được CI kiểm tra tự động. Sửa một phần thì chỉ đọc, sửa và chạy test của phần đó.

## 1. Bản đồ backend (`backend/app/`)

### Phần nền

| Module | Làm gì | Bảng DB | Test chính |
|---|---|---|---|
| `auth` | Đăng ký, đăng nhập, JWT, refresh xoay vòng, xác minh email, rate limit đăng nhập / đăng ký | `users`, `refresh_tokens`, `email_tokens` | `test_auth.py`, `test_refresh.py`, `test_email.py`, `test_auth_ratelimit.py` |
| `courses` | Khóa học, chương, bài; catalog + cache | `courses`, `sections`, `lessons` | `test_courses.py`, `test_catalog.py`, `test_course_content.py`, `test_course_cache.py` |
| `enrollment` | Đăng ký khóa, tiến độ, quyền xem bài | `enrollments`, `lesson_progress` | `test_enrollment.py`, `test_lesson_access.py` |
| `materials` | Upload (staging → kiểm tra → key chính thức), tài liệu PDF, đoạn (chunk) | `assets`, `sources`, `source_pages`, `chunks` | `test_uploads.py`, `test_sources_api.py`, `test_chunks_db.py` |
| `jobs` | Tạo job nền chống trùng, đưa vào hàng đợi sau commit | `jobs` | `test_jobs.py`, `test_worker.py` |
| `notify` | Hộp thư đi email (outbox), gửi SMTP | `email_outbox` | `test_email.py` |

### Phần tính năng

| Module | Làm gì | Bảng DB | Test chính |
|---|---|---|---|
| `tutor` | AI Tutor: RAG, SSE, phản hồi 👍👎 | `chat_sessions`, `chat_messages` | `test_tutor_*.py` |
| `quiz` | Sinh câu hỏi bằng AI, duyệt, quiz, làm bài, chấm | `questions`, `quizzes`, `quiz_questions`, `quiz_attempts`, `attempt_answers` | `test_quiz_*.py`, `test_questions_api.py`, `test_quizzes_api.py`, `test_attempts_api.py`, `test_submit_api.py` |
| `studio` | AI Studio: hướng dẫn tài liệu, báo cáo, flashcard, ghi chú | `source_guides`, `study_artifacts`, `flashcard_reviews`, `notes` | `test_studio.py`, `test_notes.py` |
| `analytics` | Thống kê khóa cho giảng viên | (chỉ đọc) | `test_analytics.py` |
| `admin` | Duyệt giảng viên, khóa tài khoản, ẩn khóa, nhật ký, CSV, token AI | `admin_actions` | `test_admin.py` |

### Lớp dùng chung

| Thư mục | Làm gì |
|---|---|
| `core/` | Cấu hình, DB, lỗi, middleware, phân quyền, rate limit, storage, cache, metrics, `/ready` |
| `ai/` | Provider AI (giả / Gemini; sau này OpenRouter), `LLMClient` (thử lại, cache, ghi `ai_calls`), prompt, retrieval |
| `ingestion/` | PDF → trang → đoạn → embedding |
| `worker/` | Khai báo job nền cho arq (gọi vào service của module) |
| `backend/eval/` | Benchmark AI (không chạy trong server) |

### Quy tắc phụ thuộc (CI kiểm bằng `uv run lint-imports`, cấu hình ở `backend/.importlinter`)

```mermaid
flowchart TB
    subgraph F[Phần tính năng]
        TUT[tutor] ~~~ QZ[quiz] ~~~ STU[studio] ~~~ ANA[analytics] ~~~ ADM[admin]
    end
    subgraph B[Phần nền]
        AUTH[auth] ~~~ CRS[courses] ~~~ ENR[enrollment] ~~~ MAT[materials] ~~~ JOB[jobs] ~~~ NTF[notify]
    end
    subgraph L[Lớp dùng chung]
        CORE[core] ~~~ AI[ai] ~~~ ING[ingestion]
    end
    F --> B --> L
```

- Phần tính năng được dùng phần nền; **phần nền không được import phần tính năng**.
- `tutor` và `quiz` không phụ thuộc nhau.
- `notify` không phụ thuộc module nào: ai cần gửi mail thì gọi `queue_email`.
- `core`, `ai`, `ingestion` không import phần tính năng, `main` hay `worker`.
- Ngoại lệ duy nhất (ghi rõ trong `.importlinter`): `courses.service` **đọc** bảng của quiz và tutor để chặn xóa khóa đã có học viên làm bài / hỏi AI.

## 2. Bản đồ frontend (`frontend/src/`)

| Thư mục | Làm gì |
|---|---|
| `app/` | Các trang (route). `app/(main)/admin/**` là khu quản trị |
| `components/ui`, `components/app`, `components/content` | Dùng chung: nút, hộp thoại, tab lọc, khung trang, hiển thị markdown |
| `components/<tính năng>` | `auth`, `course`, `lesson`, `tutor`, `quiz`, `studio`, `teach`, `admin` |
| `lib/` | Gọi API, truy vấn TanStack Query, đăng nhập, tiện ích |

Quy tắc (ESLint `no-restricted-imports` trong `eslint.config.mjs`):

- `lib`, `components/ui`, `components/app`, `components/content` không import component của tính năng nào (trừ file test).
- `components/admin` chỉ dùng trong khu quản trị.

## 3. Sửa một phần thì làm gì

| Sửa | Chạy test trên máy | CI chạy | Deploy khởi động lại |
|---|---|---|---|
| Một module backend, ví dụ `studio` | `uv run pytest tests/test_studio.py tests/test_notes.py`, rồi `uv run lint-imports` | `lint`, `test`, `docker`, `audit`, và `frontend` (kiểm kiểu API) | `api`, `worker` |
| Lớp AI (`app/ai/`), ví dụ thêm OpenRouter | `uv run pytest tests/test_llm_*.py tests/test_ai_*.py tests/test_tutor_answer.py` | như trên | `api`, `worker` |
| Giao diện một tính năng | `npx vitest run src/components/<tính năng>`, `npx playwright test e2e/<tính năng>.spec.ts` | `frontend`, `docker`, `audit` | `web` |
| Hạ tầng (`infra/`, `docker-compose.prod.yml`) | `bash infra/deploy/test_deploy.sh` | `infra` | cả stack |
| Chỉ tài liệu (`docs/`, `*.md`) | — | chỉ job `changes` | không gì |

Trước khi push vẫn nên chạy đủ test của phía mình sửa (`uv run pytest -q` hoặc `npm test`), vì một module có thể bị module khác dùng lại.
````

- [ ] **Bước 2: Liên kết**: thêm vào đầu `docs/architecture/README.md` (ngay dưới tiêu đề):

```markdown
> Bản đồ các phần, quy tắc phụ thuộc và "sửa phần nào chạy gì": [modules.md](modules.md). ERD: [erd.md](erd.md).
```

Nếu repo có `CLAUDE.md` (hướng dẫn cho Claude Code) thì thêm một dòng: `Trước khi sửa backend/frontend, đọc docs/architecture/modules.md; giữ uv run lint-imports và npx eslint sạch.`

- [ ] **Bước 3: Commit**

```bash
git add docs
[ -f CLAUDE.md ] && git add CLAUDE.md
git commit -m "docs(architecture): module map, dependency rules and per-part workflow"
```

---

## Task 6: Kiểm tra thật trên GitHub và VPS

- [ ] **Bước 1:** Push các commit của Task 1–5. Tab Actions: lần này mọi job chạy (vì `ci.yml` đổi) và đều xanh; `Deploy` chạy cả stack (vì `infra/` đổi).
- [ ] **Bước 2: Chỉ sửa frontend**: đổi một chữ trong một trang (ví dụ tiêu đề trang Tài khoản), push.
  - CI: chỉ `changes`, `frontend`, `docker`, `audit` chạy; `lint`, `test`, `infra` hiện **skipped**.
  - Log deploy (tab Actions → Deploy): `Phần cần cập nhật: web`. Trên VPS `./infra/prod.sh ps`: chỉ `web` có thời gian khởi động mới.
- [ ] **Bước 3: Chỉ sửa tài liệu**: sửa một dòng trong `docs/`, push. CI chỉ chạy `changes`; deploy in `không khởi động lại service nào`.
- [ ] **Bước 4: Chỉ sửa backend** (ví dụ một chuỗi thông báo lỗi): CI chạy `lint`, `test`, `frontend`, `docker`, `audit`; deploy `api worker`; `web` không khởi động lại.
- [ ] **Bước 5:** Chụp màn hình tab Actions ở bước 2 và 3 (jobs skipped) cho báo cáo (phần CI/CD). Ghi thời gian CI trước / sau vào `docs/perf/report.md`, mục Vận hành:

| Loại thay đổi | Thời gian CI trước | Sau |
|---|---|---|
| Chỉ frontend | | |
| Chỉ tài liệu | | |

- [ ] **Bước 6: Commit** số liệu:

```bash
git add docs/perf/report.md && git commit -m "docs(perf): CI time per change type after path filters"
```

---

## Phụ lục: Ánh xạ yêu cầu → task

| Yêu cầu | Task |
|---|---|
| Sửa phần nào chỉ đụng phần đó (backend) | 1, 5 |
| Sửa phần nào chỉ đụng phần đó (frontend) | 2, 5 |
| CI chỉ chạy phần liên quan | 3, 6 |
| Deploy chỉ cập nhật phần bị đổi, có rollback | 4, 6 |
| Tài liệu cho người bảo trì sau này | 5 |
