# Frontend FE-1 — Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng skill `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`) để theo dõi.

**Mục tiêu:** Dựng frontend Next.js cho LMS-AI gồm nền móng, đăng nhập, catalog, trang học bài có AI Tutor (SSE, trích nguồn), trình soạn khóa cho giảng viên và upload PDF/video có tiến trình. Giao diện bám theo `docs/design/design-system.md` (dịu mắt khi học lâu, mỗi việc một nút đúng loại).

**Kiến trúc:**

- Next.js App Router. Mọi trang dữ liệu là client component dùng TanStack Query.
- Trình duyệt chỉ gọi cùng origin `/api/v1/*`, Next chuyển tiếp sang FastAPI qua `rewrites`. Vì vậy cookie refresh (`path=/api/v1/auth`, `SameSite=Lax`) chạy được mà không cần CORS.
- Access token chỉ nằm trong bộ nhớ. Gặp 401 thì refresh đúng 1 lần (single-flight) rồi gửi lại request.
- Type của API được **sinh từ OpenAPI của backend** (`openapi-typescript`), nên backend đổi schema thì `tsc` báo lỗi ngay.
- AI Tutor đọc SSE bằng `fetch` + `ReadableStream`. Không dùng `EventSource`, vì cần POST và header Authorization.

**Tech stack:** Next.js 16.3 (Turbopack), React 19.2, TypeScript, Tailwind CSS 4, Radix UI (`radix-ui`), lucide-react, TanStack Query 5, openapi-fetch 0.17, react-hook-form + zod 4, react-markdown + remark-gfm + remark-math + rehype-katex, @dnd-kit, sonner, next-themes, Fontsource. Test: Vitest 5 + Testing Library + MSW, Playwright + axe-core.

**Mã trong plan đã được chạy thử:**

- 46 unit test, 18 test E2E (9 kịch bản × 2 khung hình 375/1280px, có kiểm tra axe WCAG AA), `eslint`, `tsc` và `next build` đều qua.
- Streaming SSE đi qua rewrite của Next đã được đo: token cách nhau 0,5 giây vẫn tới đúng nhịp, không bị gom lại.
- Gõ **đúng** code trong plan. Nếu phải lệch (do phiên bản thư viện khác), ghi lại lý do trong commit message.

---

## 0. Bối cảnh cần biết trước khi làm

### 0.1 Điều kiện bắt đầu

- Backend tuần 2 đã xong (Task 1–21) cùng các bản sửa sau review: hợp đồng Tutor, chặn xóa (409), đổi tên enum, CRLF.
- Chạy được `docker compose up -d --build` và `http://localhost:8000/api/v1/health` trả 200.
- Máy có Node.js ≥ 20.9 (khuyến nghị 22 LTS). Kiểm tra bằng `node -v`.

### 0.2 Những điều backend quy định mà frontend phải theo

| Chủ đề | Quy định | Ở đâu trong FE |
|---|---|---|
| Lỗi | Thân lỗi luôn có dạng `{"error": {code, message, details, request_id}}`. 422 có `details.errors[{loc,msg}]`. 429 có header `Retry-After` | `src/lib/api/errors.ts` |
| Auth | `POST /auth/login` trả `{access_token}` và đặt cookie `refresh_token` (HttpOnly, path `/api/v1/auth`). `POST /auth/refresh` xoay vòng token, dùng lại token cũ thì báo `TOKEN_REUSED` | `src/lib/api/client.ts`, `auth-context.tsx` |
| Quyền | `require_staff` = giảng viên **đã duyệt** hoặc admin. Giảng viên `pending` gọi API soạn khóa sẽ nhận 403 | `isStaff()`, `RequireAuth staff` |
| Tiến độ | `PUT /lessons/{id}/progress` **chỉ học viên** được gọi, giảng viên nhận 403 | `useVideoProgress(track=false)` cho giảng viên |
| Video | `GET /lessons/{id}/video` trả URL đã ký (sống 1 giờ). Bài không có video thì trả 404 | `useLessonVideo` đổi 404 thành `null` |
| Upload | `POST /uploads/presign` → PUT thẳng lên MinIO → `POST /uploads/{id}/complete` (server kiểm tra magic bytes). PDF ≤ 50MB, MP4 ≤ 500MB | `src/lib/api/upload.ts` |
| Tài liệu | `POST /lessons/{id}/sources` trả 202 kèm `job_id`. Trạng thái `pending → processing → ready / failed`. `warning` có thể có cả khi `ready` | `source-list.tsx` (tự hỏi lại mỗi 3 giây) |
| SSE Tutor | Thứ tự event: `sources` → `token`… → `done` hoặc `error`. `error` **có thể là event đầu tiên**. Lỗi trước khi mở stream (403/404/422/429) là JSON thường | `use-tutor-chat.ts` |
| SSE Tutor | Token stream có thể còn `[n]` thô hoặc phần bị lọc, nên **nội dung cuối lấy từ `done.content`**. Khi từ chối trả lời (`refused`) vẫn có `sources` | `use-tutor-chat.ts` |
| Xóa | Xóa khóa, chương hoặc bài đã có dữ liệu học viên thì trả **409** kèm message. Hộp thoại xác nhận phải giữ nguyên và hiện message đó | `ConfirmDialog` + toast |
| Slug | Slug sinh **một lần lúc tạo khóa** và không đổi khi đổi tên khóa. Vì vậy URL trình soạn dùng slug | `/teach/[slug]` |

### 0.3 Next.js 16: những điểm khác bản cũ

- Turbopack là mặc định cho cả `dev` và `build`.
- `params` trong page là Promise. Plan né chuyện này bằng cách dùng `useParams()` trong client component.
- `middleware` đổi tên thành `proxy`. FE-1 không dùng.
- `create-next-app` tạo thêm `AGENTS.md` và `CLAUDE.md` trong `frontend/`, dặn agent đọc tài liệu trong `node_modules/next/dist/docs/` trước khi viết code. **Giữ nguyên 2 file đó.**
- **`rewrites` được "đóng băng" lúc build:** `API_ORIGIN` phải có giá trị lúc chạy `next build`, không phải lúc `next start`. Docker truyền nó qua build arg (xem Task 17).

### 0.4 Cấu trúc thư mục

```
frontend/
├── next.config.ts            # rewrites /api/v1 → API_ORIGIN, output standalone
├── vitest.config.mts · playwright.config.ts · Dockerfile · .env.example
├── openapi.json              # xuất từ backend (npm run gen:api), có commit
├── e2e/                      # Playwright: mock-api.ts, a11y.ts, *.spec.ts
└── src/
    ├── app/
    │   ├── layout.tsx · globals.css            # font, token màu 3 theme, khung đọc .reader
    │   ├── (auth)/login · register             # trang không có khung điều hướng
    │   ├── (main)/layout.tsx                   # AppShell: thanh bên / thanh dưới
    │   ├── (main)/page.tsx · explore · courses/[slug] · my · account
    │   ├── (main)/teach · teach/[slug] · teach/[slug]/lessons/[lessonId]
    │   └── learn/[slug]/[lessonId]             # trang học bài, layout riêng
    ├── components/
    │   ├── ui/        # button, input(Field), misc(Badge, Progress, Tip…), dialog(Confirm, Sheet), menu
    │   ├── app/       # providers, app-shell, nav-items, theme-switcher, states
    │   ├── content/   # markdown (KaTeX, GFM, không render HTML thô)
    │   ├── course/    # course-card, my-course-list
    │   ├── lesson/    # lesson-view, course-outline, reading-progress, break-reminder, shortcut-help
    │   ├── tutor/     # tutor-panel, citation-chip
    │   └── teach/     # course-editor, curriculum, lesson-editor, source-list, file-drop, inline-add
    ├── lib/
    │   ├── api/       # schema.d.ts (sinh), token, errors, client, sse, upload
    │   ├── auth/      # auth-context, require-auth, safe-next
    │   ├── study/     # storage, use-break-reminder, use-shortcuts, use-video-progress, resume
    │   ├── tutor/     # types, citations, use-tutor-chat
    │   ├── queries.ts · teach-queries.ts · use-autosave.ts · use-debounced.ts · use-mounted.ts · utils.ts
    └── test/          # setup.ts, msw.ts
```

### 0.5 Quy ước

- **Chữ hiển thị bằng tiếng Việt, tên biến bằng tiếng Anh.** Chữ trên nút là động từ cụ thể ("Gửi", "Xuất bản"), theo bảng hành động → nút ở design-system §5.3.
- Mọi màn hình dữ liệu có đủ 4 trạng thái: skeleton (`aria-busy`), trống (`EmptyState`), lỗi (`ErrorState` kèm Thử lại và `request_id`), có dữ liệu.
- Mỗi vùng nhìn **tối đa 1 nút `default`** (nút chính). Xóa luôn dùng `destructive-outline`, đặt trong menu `⋯` hoặc vùng nguy hiểm, và luôn qua `ConfirmDialog`.
- Nút chỉ có icon thì bắt buộc có `aria-label` và bọc trong `<Tip>`.
- **localStorage** chỉ dùng cho tiện ích (cỡ chữ, bài gần nhất, vị trí cuộn, nhắc nghỉ), qua `src/lib/study/storage.ts`. Mọi truy cập đều bọc try/catch.
- Commit sau mỗi task theo dạng `feat(web): …` / `test(web): …` / `chore(web): …`. **Không** thêm trailer `Co-Authored-By` hay `Claude-Session`: lịch sử repo đã bỏ hết các dòng này, author là chủ repo.
- Lệnh chạy từ thư mục `frontend/`, trừ khi ghi khác. Trên Windows dùng PowerShell. Các lệnh `npm`/`npx` y hệt trên mọi hệ điều hành.

### 0.6 Lệnh kiểm tra (dùng ở cuối mỗi task)

```bash
npm run lint && npm run typecheck && npm test
```

Expected: không có lỗi eslint và `tsc`, Vitest báo mọi test PASS.

---

## Task 1: Khởi tạo dự án Next.js và bộ công cụ test

**Files:**
- Create: `frontend/` (bằng `create-next-app`), `frontend/next.config.ts`, `frontend/vitest.config.mts`, `frontend/src/test/setup.ts`, `frontend/src/test/msw.ts`, `frontend/.env.example`
- Modify: `frontend/package.json` (scripts), `frontend/.gitignore`
- Delete: `frontend/src/app/page.tsx`, `frontend/public/*.svg`

- [x] **Bước 1: Tạo dự án** (chạy ở thư mục gốc repo)

```bash
npx create-next-app@16 frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm --yes
```

Expected: có thư mục `frontend/` với Next `16.x`, React `19.x`, Tailwind `^4`. Nếu `create-next-app` tự `git init` trong `frontend/` thì xóa thư mục `frontend/.git`, vì repo đã có git ở thư mục gốc.

- [x] **Bước 2: Cài thư viện**

```bash
cd frontend
npm i radix-ui class-variance-authority clsx tailwind-merge lucide-react next-themes sonner @tanstack/react-query openapi-fetch react-markdown remark-gfm remark-math rehype-katex katex @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities react-hook-form zod @hookform/resolvers @fontsource/be-vietnam-pro @fontsource-variable/noto-sans @fontsource-variable/jetbrains-mono
npm i -D @types/node@^22 vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/dom @testing-library/user-event @testing-library/jest-dom msw openapi-typescript @playwright/test @axe-core/playwright
```

Expected: cài không lỗi. `@types/node` phải là `^22`, vì Vitest 5 không nhận `@types/node@20` (lỗi ERESOLVE).

> **Vì sao dùng Fontsource thay vì `next/font/google`?** Font được đóng gói sẵn trong `node_modules`, nên `next build` (kể cả trong Docker, CI) không cần tải từ Google, và trang không gửi request nào tới Google. Đây là lệch nhỏ so với design-system §3, kết quả hiển thị giống hệt.

- [x] **Bước 3: Thêm scripts vào `package.json`** (giữ nguyên `dev`, `build`, `start`, `lint` có sẵn)

```json
"typecheck": "tsc --noEmit",
"test": "vitest run",
"test:watch": "vitest",
"e2e": "playwright test",
"api:export": "uv run --directory ../backend python -m scripts.export_openapi ../frontend/openapi.json",
"gen:api": "npm run api:export && openapi-typescript openapi.json -o src/lib/api/schema.d.ts"
```

- [x] **Bước 4: Ghi `next.config.ts`**

```ts
import type { NextConfig } from "next";

// Trình duyệt chỉ gọi cùng origin (/api/v1/...), Next chuyển tiếp sang FastAPI.
// Nhờ vậy cookie refresh (path=/api/v1/auth, SameSite=Lax) hoạt động mà không cần CORS.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` }];
  },
};

export default nextConfig;
```

- [x] **Bước 5: Cấu hình Vitest**

`vitest.config.mts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
```

`src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./msw";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  localStorage.clear();
});
afterAll(() => server.close());
```

`src/test/msw.ts`:

```ts
import { setupServer } from "msw/node";

// Mỗi test tự thêm handler bằng server.use(...). Base URL của jsdom là http://localhost:3000.
export const server = setupServer();
export const api = (path: string) => `http://localhost:3000/api/v1${path}`;
```

- [x] **Bước 6: File môi trường và `.gitignore`**

`.env.example`:

```bash
# Địa chỉ FastAPI mà Next chuyển tiếp /api/v1/* tới (đọc lúc `next dev` / `next build`).
API_ORIGIN=http://localhost:8000
# Chỉ đặt khi muốn trình duyệt gọi thẳng API (bỏ qua rewrite), vd. http://localhost:8000
# Khi đó backend phải có CORS_ORIGINS chứa origin của frontend.
# NEXT_PUBLIC_API_BASE=
```

Trong `.gitignore`, ngay dưới dòng `.env*`, thêm `!.env.example`. Cuối file thêm:

```
# playwright
/test-results/
/playwright-report/
```

Copy `.env.example` thành `.env.local` (file này không commit).

- [x] **Bước 7: Dọn file mẫu**

```bash
rm -rf .next src/app/page.tsx public/*.svg && touch public/.gitkeep
```

Phải xóa `.next` vì `create-next-app` đã sinh sẵn type route trỏ tới `page.tsx`. Không xóa thì `tsc` sẽ báo `Cannot find module '../../src/app/page.js'`. Trên PowerShell dùng lệnh: `Remove-Item -Recurse -Force .next, src/app/page.tsx, public/*.svg; New-Item public/.gitkeep`.

- [x] **Bước 8: Kiểm tra**

```bash
npm run typecheck && npx vitest run --passWithNoTests
```

Expected: `tsc` không lỗi; Vitest báo `No test files found` và thoát mã 0.

- [x] **Bước 9: Commit**

```bash
cd .. && git add frontend && git commit -m "chore(web): scaffold Next.js 16 frontend with Vitest and MSW"
```

---

## Task 2: Design tokens, 3 chế độ màu, khung đọc

**Files:**
- Modify: `frontend/src/app/globals.css` (thay toàn bộ)

Token lấy đúng từ design-system §2: 3 bộ màu `:root` (Sáng), `.dark` (Tối dịu), `.sepia` (Giấy), đã kiểm tra độ tương phản. Lớp `.reader` là khung đọc dùng chung cho nội dung bài và câu trả lời AI: chữ 17px chỉnh được qua biến `--reader-size`, giãn dòng 1.75, tối đa 68 ký tự mỗi dòng.

- [x] **Bước 1: Ghi `src/app/globals.css`**

```css
@import "tailwindcss";
@import "katex/dist/katex.min.css";

@custom-variant dark (&:is(.dark *));

/* ---- Design tokens (docs/design/design-system.md §2) ---- */
:root {
  --background: #f7f5f0;
  --surface: #fffdf9;
  --foreground: #24292f;
  --muted-foreground: #5b6470;
  --border: #e3ded4;
  --muted: #efebe3;
  --primary: #0f6e66;
  --primary-foreground: #ffffff;
  --accent: #a15c07;
  --success: #2f7d4f;
  --destructive: #b42318;
  --ring: #0f6e66;
  --radius: 10px;
  --reader-size: 17px;
}

.dark {
  --background: #171a1e;
  --surface: #1f2328;
  --foreground: #e4e1da;
  --muted-foreground: #a3a8af;
  --border: #33383f;
  --muted: #262b31;
  --primary: #5fbfb3;
  --primary-foreground: #0e1a19;
  --accent: #e0a458;
  --success: #7cc49a;
  --destructive: #f2867a;
  --ring: #5fbfb3;
  color-scheme: dark;
}

.sepia {
  --background: #f3ead7;
  --surface: #f9f2e3;
  --foreground: #3a2f24;
  --muted-foreground: #6b5b49;
  --border: #ddcfb4;
  --muted: #ebe0c9;
  --primary: #2f6b5e;
  --primary-foreground: #ffffff;
  --accent: #8a5313;
  --success: #3b6e45;
  --destructive: #a3321f;
  --ring: #2f6b5e;
}

@theme inline {
  --color-background: var(--background);
  --color-surface: var(--surface);
  --color-foreground: var(--foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-border: var(--border);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-accent: var(--accent);
  --color-success: var(--success);
  --color-destructive: var(--destructive);
  --color-ring: var(--ring);
  --radius-lg: var(--radius);
  --radius-md: 8px;
  --font-sans: "Be Vietnam Pro", system-ui, sans-serif;
  --font-reading: "Noto Sans Variable", "Noto Sans", system-ui, sans-serif;
  --font-mono: "JetBrains Mono Variable", ui-monospace, monospace;
}

@layer base {
  * {
    border-color: var(--border);
  }
  body {
    background: var(--background);
    color: var(--foreground);
    font-family: var(--font-sans);
  }
  :focus-visible {
    outline: 2px solid var(--ring);
    outline-offset: 2px;
  }
}

/* Khung đọc nội dung bài / câu trả lời AI (design-system §3) */
.reader {
  font-family: var(--font-reading);
  font-size: var(--reader-size);
  line-height: 1.75;
  max-width: 68ch;
  overflow-wrap: anywhere;
}
.reader h1, .reader h2, .reader h3 {
  font-family: var(--font-sans);
  font-weight: 600;
  line-height: 1.35;
  margin: 1.6em 0 0.6em;
  scroll-margin-top: 80px;
}
.reader h1 { font-size: 1.6em; }
.reader h2 { font-size: 1.35em; }
.reader h3 { font-size: 1.15em; }
.reader p, .reader ul, .reader ol, .reader pre, .reader table, .reader blockquote { margin: 0 0 1em; }
.reader ul { list-style: disc; padding-left: 1.4em; }
.reader ol { list-style: decimal; padding-left: 1.4em; }
.reader a { color: var(--primary); text-decoration: underline; text-underline-offset: 3px; }
.reader code {
  font-family: var(--font-mono);
  font-size: 0.85em;
  background: var(--muted);
  padding: 0.1em 0.35em;
  border-radius: 4px;
}
.reader pre {
  background: var(--muted);
  padding: 12px 14px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 14px;
  line-height: 1.6;
}
.reader pre code { background: none; padding: 0; font-size: inherit; }
.reader blockquote { border-left: 3px solid var(--accent); padding-left: 1em; color: var(--muted-foreground); }
.reader table { border-collapse: collapse; display: block; overflow-x: auto; }
.reader th, .reader td { border: 1px solid var(--border); padding: 6px 10px; }
.reader .katex-display { overflow-x: auto; overflow-y: hidden; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [x] **Bước 2: Kiểm tra build CSS**

```bash
npm run build
```

Expected: build thành công. Layout mặc định của `create-next-app` vẫn còn (đến Task 7 mới thay), và tạm thời chưa có route `/`, chuyện đó không sao.

- [x] **Bước 3: Commit**

```bash
git add frontend/src/app/globals.css && git commit -m "feat(web): design tokens for light, dim and sepia themes plus reader styles"
```

---

## Task 3: Bộ component UI cơ bản (nút, ô nhập, hộp thoại, menu)

**Files:**
- Create: `frontend/src/lib/utils.ts`, `frontend/src/components/ui/button.tsx`, `input.tsx`, `misc.tsx`, `dialog.tsx`, `menu.tsx`
- Test: `frontend/src/components/ui/button.test.tsx`

Không dùng `shadcn` CLI (CLI phải tải registry qua mạng, mạng công ty/CI có thể chặn). Code dưới đây viết cùng phong cách shadcn, trên `radix-ui`, đã được map sẵn theo design-system §5:

- 5 variant: `default` (Chính), `outline` (Phụ), `ghost` (Nhẹ), `destructive-outline` → `destructive` (Nguy hiểm), `link` (Liên kết).
- 4 cỡ: `default` 40px, `lg` 48px, `sm` 32px, `icon` 40×40.
- Prop `loading` / `loadingText` cho trạng thái "Đang …".

- [x] **Bước 1: `src/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [x] **Bước 2: Viết test cho Button (sẽ fail)**

`src/components/ui/button.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("khi loading: bị khóa, aria-busy và đổi chữ", () => {
    render(
      <Button loading loadingText="Đang nộp…">
        Nộp bài
      </Button>,
    );
    const btn = screen.getByRole("button", { name: "Đang nộp…" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
  });

  it("mặc định là nút chính cao 40px", () => {
    render(<Button>Gửi câu hỏi</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-primary", "h-10");
  });
});
```

- [x] **Bước 3: Chạy test, xác nhận fail**

Run: `npx vitest run src/components/ui/button.test.tsx`
Expected: FAIL, lỗi `Failed to resolve import "./button"`.

- [x] **Bước 4: Viết `src/components/ui/button.tsx`**

```tsx
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { Slot } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

// design-system §5: 5 loại nút, 4 cỡ, trạng thái đang xử lý bắt buộc
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-border bg-transparent hover:bg-muted",
        ghost: "hover:bg-muted",
        "destructive-outline": "border border-destructive/60 text-destructive hover:bg-destructive/10",
        destructive: "bg-destructive text-primary-foreground hover:bg-destructive/90 dark:text-background",
        link: "h-auto px-0 text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4",
        lg: "h-12 px-6 text-base",
        sm: "h-8 px-3",
        icon: "size-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
    /** Đang xử lý: khóa nút, hiện vòng xoay và đổi chữ thành loadingText. */
    loading?: boolean;
    loadingText?: string;
  };

export function Button({
  className,
  variant,
  size,
  asChild,
  loading = false,
  loadingText,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={asChild ? undefined : disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && !asChild ? (
        <>
          <Loader2 className="animate-spin" aria-hidden />
          {loadingText ?? children}
        </>
      ) : (
        children
      )}
    </Comp>
  );
}
```

- [x] **Bước 5: Chạy test, xác nhận pass**

Run: `npx vitest run src/components/ui/button.test.tsx`
Expected: PASS (2 test).

- [x] **Bước 6: Các component còn lại**

`src/components/ui/input.tsx` gồm `Input`, `Textarea`, `Label`, và `Field`. `Field` có nhãn, lỗi hiện ngay bên dưới, tự gắn `aria-invalid` và `aria-describedby`:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-md border border-border bg-surface px-3 text-base md:text-sm placeholder:text-muted-foreground aria-invalid:border-destructive disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "w-full rounded-md border border-border bg-surface px-3 py-2 text-base md:text-sm placeholder:text-muted-foreground aria-invalid:border-destructive",
        className,
      )}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium", className)} {...props} />;
}

/** Ô nhập có nhãn + lỗi ngay bên dưới (aria-describedby). */
export function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactElement<{ id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string }>;
}) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {React.cloneElement(children, { id, "aria-invalid": !!error || undefined, "aria-describedby": describedBy })}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
```

`src/components/ui/misc.tsx` gồm `Skeleton`, `Badge`, `Progress`, `TooltipProvider`, và `Tip` (tooltip bắt buộc cho nút chỉ có icon):

```tsx
import { Progress as ProgressPrimitive, Tooltip as TooltipPrimitive } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.ComponentProps<"span"> & { tone?: "neutral" | "primary" | "success" | "accent" | "destructive" }) {
  const tones = {
    neutral: "border-border text-muted-foreground",
    primary: "border-primary/40 text-primary",
    success: "border-success/40 text-success",
    accent: "border-accent/40 text-accent",
    destructive: "border-destructive/40 text-destructive",
  };
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium", tones[tone], className)}
      {...props}
    />
  );
}

export function Progress({ value, className, label }: { value: number; className?: string; label: string }) {
  return (
    <ProgressPrimitive.Root
      value={value}
      aria-label={label}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <ProgressPrimitive.Indicator
        className="h-full bg-accent transition-transform duration-200"
        style={{ transform: `translateX(-${100 - Math.min(100, Math.max(0, value))}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}

export const TooltipProvider = TooltipPrimitive.Provider;

/** Tooltip bắt buộc cho nút chỉ có icon (design-system §5.1). */
export function Tip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          className="z-50 rounded-md bg-foreground px-2 py-1 text-xs text-background shadow"
        >
          {label}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
```

`src/components/ui/dialog.tsx` gồm:

- `Dialog`, `DialogContent`.
- `Sheet`: khung trượt từ dưới lên, cao 85%, hoặc từ trái sang.
- `ConfirmDialog`: tiêu đề là câu hỏi, nút **Hủy được focus sẵn**, có tùy chọn bắt gõ lại tên để xác nhận. Nếu `onConfirm` ném lỗi thì hộp thoại **vẫn mở** (ví dụ khi xóa bị 409).

```tsx
"use client";

import { X } from "lucide-react";
import { AlertDialog as AD, Dialog as D } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

const overlay = "fixed inset-0 z-40 bg-black/40";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <D.Portal>
      <D.Overlay className={overlay} />
      <D.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-surface p-6 shadow-lg",
          className,
        )}
      >
        <D.Title className="text-lg font-semibold">{title}</D.Title>
        {description ? <D.Description className="mt-2 text-sm text-muted-foreground">{description}</D.Description> : null}
        <div className="mt-4">{children}</div>
        <D.Close asChild>
          <Button variant="ghost" size="icon" aria-label="Đóng" className="absolute right-2 top-2">
            <X />
          </Button>
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}

/** Khung trượt: từ dưới lên trên điện thoại (85% chiều cao) — dùng cho Tutor, mục lục. */
export function Sheet({
  open,
  onOpenChange,
  title,
  side = "bottom",
  children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  side?: "bottom" | "left";
  children: React.ReactNode;
}) {
  const pos =
    side === "bottom"
      ? "inset-x-0 bottom-0 h-[85dvh] rounded-t-lg border-t"
      : "inset-y-0 left-0 w-[85vw] max-w-sm border-r";
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className={overlay} />
        <D.Content className={cn("fixed z-50 flex flex-col bg-surface shadow-lg", pos)} aria-describedby={undefined}>
          <div className="flex h-12 shrink-0 items-center justify-between border-b px-4">
            <D.Title className="font-semibold">{title}</D.Title>
            <D.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Đóng">
                <X />
              </Button>
            </D.Close>
          </div>
          <div className="min-h-0 flex-1">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

/**
 * Hộp thoại xác nhận (design-system §6): tiêu đề là câu hỏi, nút Hủy được focus sẵn,
 * nút hành động ghi động từ cụ thể. `onConfirm` trả Promise → nút hiện "đang xử lý".
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  pendingLabel,
  destructive = false,
  onConfirm,
  confirmText,
  children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  pendingLabel?: string;
  destructive?: boolean;
  onConfirm: () => Promise<unknown> | void;
  /** Nếu có: người dùng phải gõ đúng chuỗi này mới bấm được (xóa khóa học). */
  confirmText?: string;
  children?: React.ReactNode;
}) {
  const [pending, setPending] = React.useState(false);
  const [typed, setTyped] = React.useState("");
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const blocked = confirmText !== undefined && typed.trim() !== confirmText;

  async function handle(e: React.MouseEvent) {
    e.preventDefault();
    setPending(true);
    try {
      await onConfirm();
      onOpenChange(false);
      setTyped("");
    } catch {
      // lỗi đã được nơi gọi báo (toast); giữ hộp thoại mở
    } finally {
      setPending(false);
    }
  }

  return (
    <AD.Root open={open} onOpenChange={onOpenChange}>
      <AD.Portal>
        <AD.Overlay className={overlay} />
        <AD.Content
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            cancelRef.current?.focus();
          }}
          className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-surface p-6 shadow-lg"
        >
          <AD.Title className="text-lg font-semibold">{title}</AD.Title>
          <AD.Description asChild>
            <div className="mt-2 text-sm text-muted-foreground">{description}</div>
          </AD.Description>
          {children}
          {confirmText !== undefined ? (
            <label className="mt-4 block text-sm">
              Gõ <strong>{confirmText}</strong> để xác nhận
              <input
                className="mt-1.5 h-10 w-full rounded-md border bg-surface px-3"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
            </label>
          ) : null}
          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <AD.Cancel asChild>
              <Button ref={cancelRef} variant="outline" disabled={pending}>
                Hủy
              </Button>
            </AD.Cancel>
            <AD.Action asChild>
              <Button
                variant={destructive ? "destructive" : "default"}
                loading={pending}
                loadingText={pendingLabel}
                disabled={blocked}
                onClick={handle}
              >
                {confirmLabel}
              </Button>
            </AD.Action>
          </div>
        </AD.Content>
      </AD.Portal>
    </AD.Root>
  );
}
```

`src/components/ui/menu.tsx` (menu `⋯`, mỗi mục cao 40px):

```tsx
"use client";

import { DropdownMenu as M } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Menu = M.Root;
export const MenuTrigger = M.Trigger;
export const MenuSeparator = () => <M.Separator className="my-1 h-px bg-border" />;

export function MenuContent({ children, align = "end" }: { children: React.ReactNode; align?: "start" | "end" }) {
  return (
    <M.Portal>
      <M.Content
        align={align}
        sideOffset={6}
        className="z-50 min-w-48 rounded-md border bg-surface p-1 shadow-md"
      >
        {children}
      </M.Content>
    </M.Portal>
  );
}

export function MenuItem({
  className,
  destructive,
  ...props
}: React.ComponentProps<typeof M.Item> & { destructive?: boolean }) {
  return (
    <M.Item
      className={cn(
        "flex min-h-10 cursor-default select-none items-center gap-2 rounded-sm px-2 text-sm outline-none data-[highlighted]:bg-muted [&_svg]:size-4",
        destructive && "text-destructive",
        className,
      )}
      {...props}
    />
  );
}
```

- [x] **Bước 7: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend/src && git commit -m "feat(web): UI primitives mapped to the design-system button rules"
```

Expected: lint và tsc sạch, 2 test PASS.

---

## Task 4: Sinh type TypeScript từ OpenAPI của backend

**Files:**
- Create: `backend/scripts/export_openapi.py`, `frontend/openapi.json` (sinh ra), `frontend/src/lib/api/schema.d.ts` (sinh ra)

- [x] **Bước 1: Script xuất OpenAPI** (`backend/scripts/export_openapi.py`)

```python
"""Xuất OpenAPI schema ra file JSON để frontend sinh type TypeScript.

Chạy từ thư mục backend/:  uv run python -m scripts.export_openapi ../frontend/openapi.json
(Ghi file trực tiếp bằng UTF-8, không dùng `>` vì PowerShell sẽ ghi UTF-16.)"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Đã ghi {out}")


if __name__ == "__main__":
    main()
```

- [x] **Bước 2: Sinh type**

```bash
npm run gen:api
```

Expected:

- Dòng `Đã ghi ../frontend/openapi.json`.
- `✨ openapi-typescript …` → `src/lib/api/schema.d.ts`.
- Mở `schema.d.ts` thấy có `"/api/v1/tutor/sessions/{session_id}/messages"` và `components["schemas"]["CourseDetail"]`.

> Nếu `uv` báo thiếu biến môi trường thì chạy lệnh trong `backend/` với `.env` sẵn có. Script chỉ import `app.main`, không kết nối DB.

- [x] **Bước 3: Commit**

```bash
cd .. && git add backend/scripts/export_openapi.py frontend/openapi.json frontend/src/lib/api/schema.d.ts
git commit -m "chore(web): generate API types from backend OpenAPI"
```

> **Quy tắc từ giờ:** mỗi khi backend đổi schema hoặc route, chạy `npm run gen:api` rồi commit cả 2 file sinh ra. CI (Task 17) sẽ fail nếu quên.

---

## Task 5: API client: token trong bộ nhớ, refresh một lần, lỗi chuẩn hóa

**Files:**
- Create: `frontend/src/lib/api/token.ts`, `errors.ts`, `client.ts`
- Test: `frontend/src/lib/api/client.test.ts`

- [x] **Bước 1: Viết test (sẽ fail)**

`src/lib/api/client.test.ts`:

```ts
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { api as url, server } from "@/test/msw";
import { api, unwrap } from "./client";
import { ApiError } from "./errors";
import { getAccessToken, setAccessToken } from "./token";

describe("api client", () => {
  beforeEach(() => setAccessToken(null));

  it("gắn Bearer token vào request", async () => {
    setAccessToken("t1");
    server.use(
      http.get(url("/me"), ({ request }) =>
        HttpResponse.json({ id: "u1", auth: request.headers.get("Authorization") }),
      ),
    );
    const me = (await unwrap(api.GET("/api/v1/me"))) as unknown as { auth: string };
    expect(me.auth).toBe("Bearer t1");
  });

  it("gặp 401 thì refresh đúng 1 lần cho nhiều request song song rồi gửi lại", async () => {
    setAccessToken("old");
    let refreshCalls = 0;
    server.use(
      http.get(url("/me"), ({ request }) =>
        request.headers.get("Authorization") === "Bearer new"
          ? HttpResponse.json({ id: "u1" })
          : HttpResponse.json({ error: { code: "INVALID_TOKEN", message: "x" } }, { status: 401 }),
      ),
      http.post(url("/auth/refresh"), () => {
        refreshCalls += 1;
        return HttpResponse.json({ access_token: "new", token_type: "bearer" });
      }),
    );
    await Promise.all([unwrap(api.GET("/api/v1/me")), unwrap(api.GET("/api/v1/me"))]);
    expect(refreshCalls).toBe(1);
    expect(getAccessToken()).toBe("new");
  });

  it("refresh thất bại thì xóa token và ném ApiError 401", async () => {
    setAccessToken("old");
    server.use(
      http.get(url("/me"), () =>
        HttpResponse.json({ error: { code: "INVALID_TOKEN", message: "Phiên hết hạn" } }, { status: 401 }),
      ),
      http.post(url("/auth/refresh"), () =>
        HttpResponse.json({ error: { code: "INVALID_TOKEN", message: "x" } }, { status: 401 }),
      ),
    );
    await expect(unwrap(api.GET("/api/v1/me"))).rejects.toMatchObject({ status: 401 });
    expect(getAccessToken()).toBeNull();
  });

  it("đọc code, message, request_id và Retry-After từ thân lỗi", async () => {
    server.use(
      http.get(url("/me"), () =>
        HttpResponse.json(
          { error: { code: "RATE_LIMITED", message: "Chậm lại", details: {}, request_id: "rq-1" } },
          { status: 429, headers: { "Retry-After": "40" } },
        ),
      ),
    );
    const err = (await unwrap(api.GET("/api/v1/me")).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "RATE_LIMITED", requestId: "rq-1", retryAfter: 40 });
  });
});
```

- [x] **Bước 2: Chạy, xác nhận fail**

Run: `npx vitest run src/lib/api/client.test.ts`
Expected: FAIL, lỗi `Failed to resolve import "./client"`.

- [x] **Bước 3: Cài đặt**

`src/lib/api/token.ts`:

```ts
// Access token chỉ nằm trong bộ nhớ (không localStorage) để giảm rủi ro XSS.
// Refresh token là cookie HttpOnly do backend đặt, JS không đọc được.
let accessToken: string | null = null;
const listeners = new Set<(t: string | null) => void>();

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
  listeners.forEach((l) => l(token));
}

export function onAccessTokenChange(listener: (t: string | null) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
```

`src/lib/api/errors.ts`:

```ts
export type ApiErrorBody = {
  error: { code: string; message: string; details?: Record<string, unknown>; request_id?: string | null };
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId: string | null = null,
    public details: Record<string, unknown> = {},
    public retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Lỗi 422 của một trường cụ thể, vd. fieldError("email"). */
  fieldError(field: string): string | undefined {
    const errors = (this.details.errors ?? []) as { loc: (string | number)[]; msg: string }[];
    return errors.find((e) => e.loc[e.loc.length - 1] === field)?.msg;
  }
}

const NETWORK_MESSAGE = "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.";

export async function toApiError(res: Response): Promise<ApiError> {
  const retryAfterHeader = res.headers.get("Retry-After");
  const retryAfter = retryAfterHeader ? Number(retryAfterHeader) : null;
  const requestId = res.headers.get("x-request-id");
  try {
    const body = (await res.clone().json()) as ApiErrorBody;
    if (body?.error?.code) {
      const e = body.error;
      return new ApiError(res.status, e.code, e.message, e.request_id ?? requestId, e.details ?? {}, retryAfter);
    }
  } catch {
    // thân không phải JSON (vd. 502 từ proxy)
  }
  const message = res.status >= 500 ? "Máy chủ đang gặp sự cố. Thử lại sau ít phút." : "Yêu cầu không hợp lệ";
  return new ApiError(res.status, "HTTP_ERROR", message, requestId, {}, retryAfter);
}

export function networkError(): ApiError {
  return new ApiError(0, "NETWORK_ERROR", NETWORK_MESSAGE);
}

/** Câu thông báo cho người dùng từ một lỗi bất kỳ. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429 && err.retryAfter) return `Bạn thao tác hơi nhanh, thử lại sau ${err.retryAfter} giây.`;
    return err.message;
  }
  return "Đã có lỗi xảy ra. Thử lại nhé.";
}
```

`src/lib/api/client.ts`:

```ts
import createClient, { type Middleware } from "openapi-fetch";
import { ApiError, networkError, toApiError } from "./errors";
import type { paths } from "./schema";
import { getAccessToken, setAccessToken } from "./token";

/** Gốc URL của API. Mặc định cùng origin với trang (Next rewrites /api/v1 → FastAPI). */
export function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE;
  return typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
}

let refreshing: Promise<string | null> | null = null;

/** Gọi /auth/refresh đúng 1 lần dù nhiều request cùng gặp 401 (single-flight). */
export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${apiBase()}/api/v1/auth/refresh`, { method: "POST", credentials: "include" });
      if (!res.ok) {
        setAccessToken(null);
        return null;
      }
      const { access_token } = (await res.json()) as { access_token: string };
      setAccessToken(access_token);
      return access_token;
    } catch {
      return null; // lỗi mạng: giữ nguyên trạng thái, không đăng xuất
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

const NO_REFRESH = ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"];

/**
 * fetch có gắn Bearer token; gặp 401 thì refresh một lần rồi gửi lại.
 * Dùng chung cho openapi-fetch, SSE và mọi lệnh gọi tay.
 */
export async function authFetch(input: Request): Promise<Response> {
  const send = (token: string | null) => {
    const req = input.clone();
    if (token) req.headers.set("Authorization", `Bearer ${token}`);
    return fetch(req, { credentials: "include" } as RequestInit);
  };
  let res: Response;
  try {
    res = await send(getAccessToken());
  } catch {
    throw networkError();
  }
  const path = new URL(input.url).pathname;
  if (res.status === 401 && !NO_REFRESH.includes(path)) {
    const token = await refreshAccessToken();
    if (token) {
      try {
        res = await send(token);
      } catch {
        throw networkError();
      }
    }
  }
  return res;
}

const throwOnError: Middleware = {
  async onResponse({ response }) {
    if (!response.ok) throw await toApiError(response);
    return response;
  },
};

// Module này chỉ được gọi từ client component, nên apiBase() chạy trong trình duyệt.
export const api = createClient<paths>({ baseUrl: apiBase(), fetch: (req) => authFetch(req) });
api.use(throwOnError);

/** Lấy `data` hoặc ném ApiError; dùng trong queryFn/mutationFn của TanStack Query. */
export async function unwrap<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined) throw error instanceof ApiError ? error : await toApiError(response);
  return data as T;
}
```

- [x] **Bước 4: Chạy, xác nhận pass**

Run: `npx vitest run src/lib/api/client.test.ts`
Expected: PASS (4 test). Riêng test "refresh đúng 1 lần cho nhiều request song song" chứng minh cơ chế single-flight, tránh bị backend coi là `TOKEN_REUSED`.

- [x] **Bước 5: Commit**

```bash
git add frontend/src/lib/api && git commit -m "feat(web): typed API client with single-flight token refresh"
```

---

## Task 6: Đọc SSE và upload có tiến trình

**Files:**
- Create: `frontend/src/lib/api/sse.ts`, `frontend/src/lib/api/upload.ts`
- Test: `frontend/src/lib/api/sse.test.ts`, `frontend/src/lib/api/upload.test.ts`

- [x] **Bước 1: Viết test SSE (sẽ fail)**

Test bao gồm event bị cắt giữa 2 chunk mạng, kể cả cắt giữa một ký tự tiếng Việt nhiều byte.

`src/lib/api/sse.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readSse } from "./sse";

function streamOf(chunks: string[]) {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((s) => c.enqueue(enc.encode(s)));
      c.close();
    },
  });
}

async function collect(chunks: string[]) {
  const out = [];
  for await (const e of readSse(streamOf(chunks))) out.push(e);
  return out;
}

describe("readSse", () => {
  it("tách các event theo dòng trống", async () => {
    const events = await collect(['event: token\ndata: {"text":"Xin"}\n\nevent: token\ndata: {"text":" chào"}\n\n']);
    expect(events).toEqual([
      { event: "token", data: '{"text":"Xin"}' },
      { event: "token", data: '{"text":" chào"}' },
    ]);
  });

  it("ghép event bị cắt giữa 2 chunk mạng, kể cả cắt giữa ký tự UTF-8", async () => {
    const full = 'event: done\ndata: {"content":"Đạo hàm"}\n\n';
    const bytes = new TextEncoder().encode(full);
    // cắt ở byte 30 (có thể nằm giữa một ký tự có dấu)
    const s = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, 30));
        c.enqueue(bytes.slice(30));
        c.close();
      },
    });
    const out = [];
    for await (const e of readSse(s)) out.push(e);
    expect(out).toEqual([{ event: "done", data: '{"content":"Đạo hàm"}' }]);
  });

  it("chấp nhận \\r\\n và bỏ qua dòng comment", async () => {
    const events = await collect([": ping\r\n\r\nevent: error\r\ndata: {\"code\":\"AI_UNAVAILABLE\"}\r\n\r\n"]);
    expect(events).toEqual([{ event: "error", data: '{"code":"AI_UNAVAILABLE"}' }]);
  });

  it("đọc được event cuối dù thiếu dòng trống kết thúc", async () => {
    expect(await collect(['event: done\ndata: {"a":1}'])).toEqual([{ event: "done", data: '{"a":1}' }]);
  });
});
```

- [x] **Bước 2: Chạy, xác nhận fail**

Run: `npx vitest run src/lib/api/sse.test.ts`
Expected: FAIL, lỗi `Failed to resolve import "./sse"`.

- [x] **Bước 3: Cài đặt `src/lib/api/sse.ts`**

```ts
export type SseEvent = { event: string; data: string };

/**
 * Đọc luồng text/event-stream từ một ReadableStream (fetch POST không dùng được EventSource).
 * Xử lý đúng khi một event bị cắt ngang giữa 2 chunk mạng, và cả xuống dòng \r\n.
 */
export async function* readSse(body: ReadableStream<Uint8Array>, signal?: AbortSignal): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) return;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const parsed = parseBlock(raw);
        if (parsed) yield parsed;
      }
    }
    const tail = parseBlock(buffer.trim());
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

function parseBlock(raw: string): SseEvent | null {
  if (!raw) return null;
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue; // comment / keep-alive
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  return data.length ? { event, data: data.join("\n") } : null;
}
```

- [x] **Bước 4: Chạy, xác nhận pass**

Run: `npx vitest run src/lib/api/sse.test.ts`
Expected: PASS (4 test).

- [x] **Bước 5: Viết test kiểm tra file (sẽ fail)**

`src/lib/api/upload.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { validateFile } from "./upload";

const file = (type: string, size: number) => {
  const f = new File(["x"], "a", { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

describe("validateFile", () => {
  it("nhận PDF đúng loại và dưới 50MB", () => {
    expect(validateFile("pdf", file("application/pdf", 1024))).toBeNull();
  });
  it("từ chối sai loại", () => {
    expect(validateFile("pdf", file("image/png", 10))).toMatch(/Chỉ nhận file PDF/);
  });
  it("từ chối file quá lớn", () => {
    expect(validateFile("video", file("video/mp4", 600 * 1024 * 1024))).toMatch(/quá lớn/);
  });
});
```

Run: `npx vitest run src/lib/api/upload.test.ts`
Expected: FAIL, lỗi `Failed to resolve import "./upload"`.

- [x] **Bước 6: Cài đặt `src/lib/api/upload.ts`**

Dùng XHR vì `fetch` chưa báo được tiến trình upload. Giới hạn dung lượng và loại file khớp `SIZE_LIMITS` và `ALLOWED_MIME` ở `backend/app/modules/materials/assets.py`.

```ts
import { api, unwrap } from "./client";

export type UploadKind = "pdf" | "video";
export type UploadProgress = (pct: number) => void;

/** PUT file lên presigned URL của MinIO bằng XHR (fetch chưa báo được tiến trình upload). */
export function putWithProgress(url: string, file: File, onProgress: UploadProgress, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload lỗi (${xhr.status})`)));
    xhr.onerror = () => reject(new Error("Mất kết nối khi tải file lên"));
    xhr.onabort = () => reject(new DOMException("Đã hủy", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(file);
  });
}

/** presign → PUT (có tiến trình) → complete. Trả về asset_id đã được server xác minh. */
export async function uploadAsset(kind: UploadKind, file: File, onProgress: UploadProgress, signal?: AbortSignal) {
  const { asset_id, put_url } = await unwrap(
    api.POST("/api/v1/uploads/presign", { body: { kind, mime: file.type, size: file.size } }),
  );
  await putWithProgress(put_url, file, onProgress, signal);
  await unwrap(api.POST("/api/v1/uploads/{asset_id}/complete", { params: { path: { asset_id } } }));
  return asset_id;
}

export const UPLOAD_RULES: Record<UploadKind, { mime: string; maxBytes: number; label: string }> = {
  pdf: { mime: "application/pdf", maxBytes: 50 * 1024 * 1024, label: "PDF, tối đa 50 MB" },
  video: { mime: "video/mp4", maxBytes: 500 * 1024 * 1024, label: "MP4, tối đa 500 MB" },
};

/** Kiểm tra trước khi gọi API, để báo lỗi ngay thay vì đợi server từ chối. */
export function validateFile(kind: UploadKind, file: File): string | null {
  const rule = UPLOAD_RULES[kind];
  if (file.type !== rule.mime) return `Chỉ nhận file ${rule.label.split(",")[0]}`;
  if (file.size > rule.maxBytes) return `File quá lớn (${rule.label})`;
  return null;
}
```

Run: `npx vitest run src/lib/api`
Expected: PASS (11 test).

- [x] **Bước 7: Commit**

```bash
git add frontend/src/lib/api && git commit -m "feat(web): SSE reader and presigned upload with progress"
```

---

## Task 7: Đăng nhập toàn cục, Providers và layout gốc

**Files:**
- Create: `frontend/src/lib/auth/auth-context.tsx`, `require-auth.tsx`, `safe-next.ts`, `frontend/src/components/app/providers.tsx`
- Modify: `frontend/src/app/layout.tsx` (thay toàn bộ)
- Test: `frontend/src/lib/auth/require-auth.test.tsx`, `frontend/src/lib/auth/safe-next.test.ts`

- [x] **Bước 1: Viết test (sẽ fail)**

`src/lib/auth/safe-next.test.ts`. Test này chặn open redirect qua `?next=`:

```ts
import { describe, expect, it } from "vitest";
import { safeNext } from "./safe-next";

describe("safeNext", () => {
  it("giữ đường dẫn nội bộ", () => expect(safeNext("/learn/a/b")).toBe("/learn/a/b"));
  it("chặn URL ngoài và //", () => {
    expect(safeNext("https://evil.com")).toBe("/");
    expect(safeNext("//evil.com")).toBe("/");
    expect(safeNext("/\\evil.com")).toBe("/");
  });
  it("rỗng thì dùng fallback", () => expect(safeNext(null, "/my")).toBe("/my"));
});
```

`src/lib/auth/require-auth.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/my" }));
const auth = { status: "anonymous", user: null as unknown };
vi.mock("./auth-context", () => ({
  useAuth: () => auth,
  isStaff: (u: { role: string; teacher_status: string } | null) => u?.teacher_status === "approved",
}));

import { RequireAuth } from "./require-auth";

describe("RequireAuth", () => {
  it("chưa đăng nhập thì chuyển tới /login kèm next", () => {
    render(<RequireAuth>nội dung</RequireAuth>);
    expect(replace).toHaveBeenCalledWith("/login?next=%2Fmy");
    expect(screen.queryByText("nội dung")).not.toBeInTheDocument();
  });

  it("giảng viên chờ duyệt thấy thông báo thay vì trang soạn khóa", () => {
    auth.status = "authenticated";
    auth.user = { role: "teacher", teacher_status: "pending" };
    render(<RequireAuth staff>soạn khóa</RequireAuth>);
    expect(screen.getByText(/đang chờ quản trị viên duyệt/)).toBeInTheDocument();
  });
});
```

Run: `npx vitest run src/lib/auth`
Expected: FAIL, lỗi `Failed to resolve import "./safe-next"` và `"./require-auth"`.

- [x] **Bước 2: Cài đặt**

`src/lib/auth/safe-next.ts`:

```ts
/** Chỉ cho phép chuyển hướng nội bộ (chặn open redirect kiểu ?next=https://evil.com hoặc //evil.com). */
export function safeNext(next: string | null | undefined, fallback = "/") {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}
```

`src/lib/auth/auth-context.tsx`. Khi mở trang, component thử refresh để khôi phục phiên. Đăng xuất thì xóa toàn bộ cache truy vấn:

```tsx
"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { api, apiBase, refreshAccessToken, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { setAccessToken } from "@/lib/api/token";

export type User = components["schemas"]["UserOut"];
type Status = "loading" | "authenticated" | "anonymous";

type AuthValue = {
  user: User | null;
  status: Status;
  login: (email: string, password: string) => Promise<User>;
  register: (data: components["schemas"]["RegisterIn"]) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = React.createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = React.useState<User | null>(null);
  const [status, setStatus] = React.useState<Status>("loading");

  const loadMe = React.useCallback(async () => {
    const me = await unwrap(api.GET("/api/v1/me"));
    setUser(me);
    setStatus("authenticated");
    return me;
  }, []);

  // Mở trang: thử khôi phục phiên từ cookie refresh.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await refreshAccessToken();
      if (cancelled) return;
      if (!token) {
        setStatus("anonymous");
        return;
      }
      try {
        await loadMe();
      } catch {
        if (!cancelled) setStatus("anonymous");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadMe]);

  const login = React.useCallback(
    async (email: string, password: string) => {
      const { access_token } = await unwrap(api.POST("/api/v1/auth/login", { body: { email, password } }));
      setAccessToken(access_token);
      return loadMe();
    },
    [loadMe],
  );

  const register = React.useCallback(async (data: components["schemas"]["RegisterIn"]) => {
    await unwrap(api.POST("/api/v1/auth/register", { body: data }));
  }, []);

  const logout = React.useCallback(async () => {
    try {
      await fetch(`${apiBase()}/api/v1/auth/logout`, { method: "POST", credentials: "include" });
    } finally {
      setAccessToken(null);
      setUser(null);
      setStatus("anonymous");
      qc.clear();
    }
  }, [qc]);

  const value = React.useMemo(() => ({ user, status, login, register, logout }), [user, status, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth phải nằm trong <AuthProvider>");
  return ctx;
}

/** Giảng viên đã duyệt hoặc admin: được tạo/sửa khóa học (khớp require_staff ở backend). */
export function isStaff(user: User | null) {
  return !!user && (user.role === "admin" || (user.role === "teacher" && user.teacher_status === "approved"));
}
```

`src/lib/auth/require-auth.tsx`:

```tsx
"use client";

import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { Skeleton } from "@/components/ui/misc";
import { isStaff, useAuth } from "./auth-context";

/** Chặn trang cần đăng nhập. Chưa đăng nhập → /login?next=<trang hiện tại>. */
export function RequireAuth({ staff = false, children }: { staff?: boolean; children: React.ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return (
      <div className="space-y-3 p-6" aria-busy="true" aria-label="Đang tải">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (staff && !isStaff(user)) {
    return (
      <div className="mx-auto max-w-md p-6 text-center">
        <h1 className="text-xl font-semibold">Bạn chưa có quyền giảng dạy</h1>
        <p className="mt-2 text-muted-foreground">
          {user?.role === "teacher"
            ? "Tài khoản giảng viên của bạn đang chờ quản trị viên duyệt."
            : "Trang này chỉ dành cho giảng viên."}
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
```

`src/components/app/providers.tsx`:

- Thứ tự bọc: theme → query → auth → tooltip.
- Toast nằm góc dưới phải trên desktop, trên cùng trên điện thoại, tắt sau 4 giây.
- Query không thử lại lỗi 4xx.

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import * as React from "react";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/misc";
import { ApiError } from "@/lib/api/errors";
import { AuthProvider } from "@/lib/auth/auth-context";

export const THEMES = ["light", "dark", "sepia"] as const;

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // không thử lại lỗi 4xx (sai quyền, không tồn tại); chỉ thử lại lỗi mạng/5xx một lần
        retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 1,
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" themes={[...THEMES]} defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        </AuthProvider>
        <ResponsiveToaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}

/** Toast: góc dưới phải trên desktop, trên cùng trên điện thoại, tự tắt 4 giây (design-system §6). */
function ResponsiveToaster() {
  const [mobile, setMobile] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return (
    <Toaster
      position={mobile ? "top-center" : "bottom-right"}
      duration={4000}
      toastOptions={{ className: "!bg-surface !text-foreground !border-border font-sans" }}
    />
  );
}
```

`src/app/layout.tsx` (thay toàn bộ file do `create-next-app` tạo):

```tsx
import "@fontsource/be-vietnam-pro/400.css";
import "@fontsource/be-vietnam-pro/500.css";
import "@fontsource/be-vietnam-pro/600.css";
import "@fontsource-variable/noto-sans";
import "@fontsource-variable/jetbrains-mono";
import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "LMS-AI", template: "%s · LMS-AI" },
  description: "Nền tảng học trực tuyến có AI Tutor trả lời theo tài liệu khóa học",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f5f0" },
    { media: "(prefers-color-scheme: dark)", color: "#171a1e" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body className="min-h-dvh antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

- [x] **Bước 3: Chạy, xác nhận pass**

Run: `npx vitest run src/lib/auth`
Expected: PASS (5 test).

- [x] **Bước 4: Commit**

```bash
git add frontend/src && git commit -m "feat(web): auth provider, route guard and root layout"
```

---

## Task 8: Khung ứng dụng: thanh bên, thanh dưới, chọn chế độ màu, 4 trạng thái

**Files:**
- Create: `frontend/src/components/app/nav-items.ts`, `app-shell.tsx`, `theme-switcher.tsx`, `states.tsx`, `frontend/src/lib/use-mounted.ts`, `frontend/src/app/(main)/layout.tsx`
- Test: `frontend/src/components/app/nav-items.test.ts`

Bố cục theo design-system §7.1:

- **≥ 1024px:** thanh bên 240px.
- **768–1023px:** thanh bên thu gọn còn icon, 64px.
- **< 768px:** thanh dưới. Các mục điều hướng cộng mục Tài khoản tổng cộng **tối đa 4**.

- [x] **Bước 1: Viết test (sẽ fail)**

`src/components/app/nav-items.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { User } from "@/lib/auth/auth-context";
import { isActive, navItems } from "./nav-items";

const user = (role: User["role"], teacher_status: User["teacher_status"] = null) =>
  ({ id: "1", email: "a@b.c", full_name: "A", role, teacher_status }) as User;

describe("navItems", () => {
  it("khách: Trang chủ, Khám phá", () => {
    expect(navItems(null).map((i) => i.label)).toEqual(["Trang chủ", "Khám phá"]);
  });
  it("học viên có Khóa của tôi", () => {
    expect(navItems(user("student")).map((i) => i.label)).toEqual(["Trang chủ", "Khám phá", "Khóa của tôi"]);
  });
  it("giảng viên đã duyệt có Khóa đang dạy; chờ duyệt thì không", () => {
    expect(navItems(user("teacher", "approved")).map((i) => i.href)).toEqual(["/teach", "/explore"]);
    expect(navItems(user("teacher", "pending")).map((i) => i.href)).toEqual(["/explore"]);
  });
  it("tối đa 3 mục (thanh dưới thêm mục Tài khoản = 4)", () => {
    for (const r of ["student", "teacher", "admin"] as const) expect(navItems(user(r, "approved")).length).toBeLessThanOrEqual(3);
  });
  it("isActive khớp tiền tố nhưng / chỉ khớp chính nó", () => {
    expect(isActive("/teach/abc", "/teach")).toBe(true);
    expect(isActive("/explore", "/")).toBe(false);
  });
});
```

Run: `npx vitest run src/components/app`
Expected: FAIL, lỗi `Failed to resolve import "./nav-items"`.

- [x] **Bước 2: Cài đặt**

`src/components/app/nav-items.ts`:

```ts
import { BookMarked, Compass, GraduationCap, Home, type LucideIcon } from "lucide-react";
import type { User } from "@/lib/auth/auth-context";
import { isStaff } from "@/lib/auth/auth-context";

export type NavItem = { href: string; label: string; icon: LucideIcon };

/** Mục điều hướng theo vai trò (design-system §7.1). Điện thoại hiển thị tối đa 4 mục. */
export function navItems(user: User | null): NavItem[] {
  const base: NavItem[] = [
    { href: "/", label: "Trang chủ", icon: Home },
    { href: "/explore", label: "Khám phá", icon: Compass },
  ];
  if (!user) return base;
  if (user.role === "student") return [...base, { href: "/my", label: "Khóa của tôi", icon: BookMarked }];
  const items: NavItem[] = [];
  if (isStaff(user)) items.push({ href: "/teach", label: "Khóa đang dạy", icon: GraduationCap });
  return [...items, ...base.slice(1)];
}

export function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
```

`src/lib/use-mounted.ts`:

```ts
import * as React from "react";

const noop = () => () => {};

/** true sau khi hydrate xong trên trình duyệt; false khi render phía server. */
export function useMounted() {
  return React.useSyncExternalStore(noop, () => true, () => false);
}
```

`src/components/app/theme-switcher.tsx` (nhóm chọn Sáng / Tối dịu / Giấy, `role="radiogroup"`):

```tsx
"use client";

import { BookOpen, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useMounted } from "@/lib/use-mounted";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Sáng", icon: Sun },
  { value: "dark", label: "Tối dịu", icon: Moon },
  { value: "sepia", label: "Giấy", icon: BookOpen },
] as const;

/** Nhóm 3 lựa chọn Sáng / Tối dịu / Giấy (design-system §5.3, phần Chung). */
export function ThemeSwitcher({ compact = false }: { compact?: boolean }) {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted(); // theme chỉ biết được trên trình duyệt
  const current = mounted ? (theme === "system" ? resolvedTheme : theme) : undefined;

  return (
    <div role="radiogroup" aria-label="Chế độ màu" className="inline-flex rounded-md border p-0.5">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={current === value}
          aria-label={compact ? label : undefined}
          title={label}
          onClick={() => setTheme(value)}
          className={cn(
            "inline-flex h-9 min-w-9 items-center justify-center gap-1.5 rounded px-2 text-sm transition-colors duration-150",
            current === value ? "bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          <Icon className="size-4" aria-hidden />
          {compact ? null : label}
        </button>
      ))}
    </div>
  );
}
```

`src/components/app/states.tsx` gồm `EmptyState`, `ErrorState` (kèm `request_id`), `CardListSkeleton`, `PageHeader`:

```tsx
import { AlertTriangle, type LucideIcon } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";

/** Trạng thái trống: icon + 1 câu + 1 hành động gợi ý (design-system §6). */
export function EmptyState({
  icon: Icon,
  title,
  action,
}: {
  icon: LucideIcon;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center">
      <Icon className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-muted-foreground">{title}</p>
      {action}
    </div>
  );
}

/** Lỗi: câu dễ hiểu + Thử lại + request_id nhỏ để báo lỗi. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border border-destructive/40 p-8 text-center">
      <AlertTriangle className="size-7 text-destructive" aria-hidden />
      <p>{errorMessage(error)}</p>
      {onRetry ? (
        <Button variant="outline" onClick={onRetry}>
          Thử lại
        </Button>
      ) : null}
      {requestId ? <p className="text-xs text-muted-foreground">Mã lỗi: {requestId}</p> : null}
    </div>
  );
}

export function CardListSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label="Đang tải">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="space-y-3 rounded-lg border p-4">
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      ))}
    </div>
  );
}

/** Tiêu đề trang: 24px điện thoại, 30px desktop, đậm 600. */
export function PageHeader({ title, actions, children }: { title: string; actions?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 md:mb-8">
      <div>
        <h1 className="text-2xl font-semibold md:text-3xl">{title}</h1>
        {children ? <div className="mt-1 text-muted-foreground">{children}</div> : null}
      </div>
      {actions}
    </div>
  );
}
```

`src/components/app/app-shell.tsx`. Có link "Bỏ qua tới nội dung" cho người dùng bàn phím:

```tsx
"use client";

import { LogIn, LogOut, User as UserIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";
import { isActive, navItems } from "./nav-items";
import { ThemeSwitcher } from "./theme-switcher";

const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

/**
 * Khung chung: thanh bên 240px (≥1024px), thu gọn icon 64px (768–1023px),
 * thanh dưới tối đa 4 mục (<768px). Trang bài học không dùng khung này.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const items = navItems(user);

  return (
    <div className="min-h-dvh md:pl-16 lg:pl-60">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        Bỏ qua tới nội dung
      </a>
      <aside className="fixed inset-y-0 left-0 hidden w-16 flex-col border-r bg-surface md:flex lg:w-60">
        <Link href="/" className="flex h-14 items-center gap-2 px-4 font-semibold">
          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">L</span>
          <span className="hidden lg:inline">LMS-AI</span>
        </Link>
        <nav aria-label="Điều hướng chính" className="flex flex-col gap-1 p-2">
          {items.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              title={label}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={cn(
                "flex h-10 items-center gap-3 rounded-md px-3 text-sm transition-colors duration-150 hover:bg-muted",
                isActive(pathname, href) && "bg-muted font-medium text-primary",
              )}
            >
              <Icon className="size-5 shrink-0" aria-hidden />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          ))}
        </nav>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur md:px-6">
        <Link href="/" className="font-semibold md:hidden">
          LMS-AI
        </Link>
        <div className="hidden md:block" />
        <AccountMenu />
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 md:px-8 md:pb-10 md:pt-8">
        {children}
      </main>

      <nav
        aria-label="Điều hướng chính"
        className="fixed inset-x-0 bottom-0 z-30 grid h-16 border-t bg-surface md:hidden"
        style={{ gridTemplateColumns: `repeat(${items.length + 1}, minmax(0, 1fr))` }}
      >
        {items.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={isActive(pathname, href) ? "page" : undefined}
            className={cn(
              "flex flex-col items-center justify-center gap-0.5 text-xs",
              isActive(pathname, href) ? "text-primary" : "text-muted-foreground",
            )}
          >
            <Icon className="size-5" aria-hidden />
            {label}
          </Link>
        ))}
        <Link
          href={user ? "/account" : "/login"}
          aria-current={isActive(pathname, "/account") ? "page" : undefined}
          className={cn(
            "flex flex-col items-center justify-center gap-0.5 text-xs",
            isActive(pathname, "/account") ? "text-primary" : "text-muted-foreground",
          )}
        >
          <UserIcon className="size-5" aria-hidden />
          {user ? "Tài khoản" : "Đăng nhập"}
        </Link>
      </nav>
    </div>
  );
}

function AccountMenu() {
  const { user, status, logout } = useAuth();
  const router = useRouter();
  if (status === "loading") return <div className="h-10 w-24" />;
  if (!user)
    return (
      <Button asChild variant="outline" className="hidden md:inline-flex">
        <Link href="/login">
          <LogIn /> Đăng nhập
        </Link>
      </Button>
    );
  return (
    <div className="hidden md:block">
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost">
            <span className="grid size-7 place-items-center rounded-full bg-muted text-xs font-semibold">
              {user.full_name.slice(0, 1).toUpperCase()}
            </span>
            {user.full_name}
          </Button>
        </MenuTrigger>
        <MenuContent>
          <div className="px-2 py-1.5 text-xs text-muted-foreground">
            {user.email} · {ROLE_LABEL[user.role]}
          </div>
          <div className="px-2 py-2">
            <ThemeSwitcher compact />
          </div>
          <MenuSeparator />
          <MenuItem
            onSelect={async () => {
              await logout();
              router.push("/");
            }}
          >
            <LogOut /> Đăng xuất
          </MenuItem>
        </MenuContent>
      </Menu>
    </div>
  );
}
```

`src/app/(main)/layout.tsx`:

```tsx
import { AppShell } from "@/components/app/app-shell";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
```

- [x] **Bước 3: Chạy, xác nhận pass**

Run: `npx vitest run src/components/app`
Expected: PASS (5 test).

- [x] **Bước 4: Commit**

```bash
git add frontend/src && git commit -m "feat(web): responsive app shell with role-based navigation"
```

---

## Task 9: Trang đăng nhập và đăng ký

**Files:**
- Create: `frontend/src/app/(auth)/layout.tsx`, `(auth)/login/page.tsx`, `(auth)/login/login-form.tsx`, `(auth)/register/page.tsx`, `(auth)/register/register-form.tsx`

Theo design-system §5.3 (phần Chung):

- Nút chính cỡ `lg`, rộng hết khung.
- Sai mật khẩu thì lỗi hiện **ngay dưới ô mật khẩu** và con trỏ quay về ô đó.
- `useSearchParams` phải nằm trong `<Suspense>`, nếu không `next build` sẽ báo lỗi.

Phần này được kiểm thử bằng E2E ở Task 16 (kịch bản "đăng nhập sai mật khẩu").

- [x] **Bước 1: Layout cho nhóm trang auth** (`src/app/(auth)/layout.tsx`)

```tsx
import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <Link href="/" className="mb-8 flex items-center gap-2 text-lg font-semibold">
        <span className="grid size-9 place-items-center rounded-md bg-primary text-primary-foreground">L</span>
        LMS-AI
      </Link>
      <main className="w-full max-w-sm rounded-lg border bg-surface p-6">{children}</main>
    </div>
  );
}
```

- [x] **Bước 2: Đăng nhập**

`src/app/(auth)/login/page.tsx`:

```tsx
import { Suspense } from "react";
import { LoginForm } from "./login-form";

export const metadata = { title: "Đăng nhập" };

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
```

`src/app/(auth)/login/login-form.tsx`:

```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNext } from "@/lib/auth/safe-next";

const schema = z.object({
  email: z.email("Email không hợp lệ"),
  password: z.string().min(1, "Nhập mật khẩu"),
});
type Values = z.infer<typeof schema>;

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: Values) {
    try {
      const user = await login(values.email, values.password);
      const fallback = user.role === "student" ? "/" : "/teach";
      router.replace(safeNext(params.get("next"), fallback));
    } catch (err) {
      // sai mật khẩu: báo ngay dưới ô mật khẩu và đưa con trỏ về đó (design-system §5.3)
      const msg = err instanceof ApiError && err.status === 401 ? "Email hoặc mật khẩu không đúng" : errorMessage(err);
      form.setError("password", { message: msg }, { shouldFocus: true });
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Đăng nhập</h1>
      <p className="mt-1 text-sm text-muted-foreground">Tiếp tục buổi học của bạn.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Field id="password" label="Mật khẩu" error={errors.password?.message}>
          <Input type="password" autoComplete="current-password" {...form.register("password")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting} loadingText="Đang đăng nhập…">
          Đăng nhập
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Chưa có tài khoản?{" "}
        <Link href={`/register${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`} className="font-medium text-primary underline underline-offset-4">
          Đăng ký
        </Link>
      </p>
    </>
  );
}
```

- [x] **Bước 3: Đăng ký**

Có chọn vai trò. Giảng viên mới đăng ký sẽ thấy thông báo "cần quản trị viên duyệt".

`src/app/(auth)/register/page.tsx`:

```tsx
import { Suspense } from "react";
import { RegisterForm } from "./register-form";

export const metadata = { title: "Đăng ký" };

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterForm />
    </Suspense>
  );
}
```

`src/app/(auth)/register/register-form.tsx`:

```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNext } from "@/lib/auth/safe-next";
import { cn } from "@/lib/utils";

const schema = z.object({
  full_name: z.string().trim().min(1, "Nhập họ tên").max(120),
  email: z.email("Email không hợp lệ"),
  password: z.string().min(8, "Mật khẩu ít nhất 8 ký tự").max(128),
  role: z.enum(["student", "teacher"]),
});
type Values = z.infer<typeof schema>;

export function RegisterForm() {
  const { register: signup, login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", password: "", role: "student" },
  });
  const { errors, isSubmitting } = form.formState;
  const role = useWatch({ control: form.control, name: "role" });

  async function onSubmit(values: Values) {
    try {
      await signup(values);
      const user = await login(values.email, values.password);
      if (user.role === "teacher") toast("Tài khoản giảng viên cần quản trị viên duyệt trước khi tạo khóa học.");
      router.replace(safeNext(params.get("next"), user.role === "student" ? "/explore" : "/teach"));
    } catch (err) {
      if (err instanceof ApiError && err.code === "EMAIL_TAKEN") {
        form.setError("email", { message: err.message }, { shouldFocus: true });
      } else {
        form.setError("root", { message: errorMessage(err) });
      }
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Tạo tài khoản</h1>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Bạn là</legend>
          <div role="radiogroup" className="grid grid-cols-2 gap-2">
            {(["student", "teacher"] as const).map((r) => (
              <label
                key={r}
                className={cn(
                  "flex h-11 cursor-pointer items-center justify-center rounded-md border text-sm",
                  role === r && "border-primary bg-primary/10 font-medium text-primary",
                )}
              >
                <input type="radio" value={r} className="sr-only" {...form.register("role")} />
                {r === "student" ? "Học viên" : "Giảng viên"}
              </label>
            ))}
          </div>
        </fieldset>
        <Field id="full_name" label="Họ và tên" error={errors.full_name?.message}>
          <Input autoComplete="name" {...form.register("full_name")} />
        </Field>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Field id="password" label="Mật khẩu" error={errors.password?.message} hint="Ít nhất 8 ký tự">
          <Input type="password" autoComplete="new-password" {...form.register("password")} />
        </Field>
        {errors.root ? (
          <p role="alert" className="text-sm text-destructive">
            {errors.root.message}
          </p>
        ) : null}
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting} loadingText="Đang tạo tài khoản…">
          Tạo tài khoản
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Đã có tài khoản?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">
          Đăng nhập
        </Link>
      </p>
    </>
  );
}
```

- [x] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm run build
git add frontend/src && git commit -m "feat(web): login and register pages"
```

Expected: build liệt kê `○ /login` và `○ /register`.

---

## Task 10: Trang học viên: trang chủ, khám phá, chi tiết khóa, khóa của tôi, tài khoản

**Files:**
- Create: `frontend/src/lib/queries.ts`, `frontend/src/lib/use-debounced.ts`, `frontend/src/lib/study/storage.ts`, `frontend/src/lib/study/resume.ts`, `frontend/src/components/course/course-card.tsx`, `frontend/src/components/course/my-course-list.tsx`, `frontend/src/components/content/markdown.tsx`
- Create pages: `frontend/src/app/(main)/page.tsx`, `explore/page.tsx`, `courses/[slug]/page.tsx`, `my/page.tsx`, `account/page.tsx`
- Test: `frontend/src/lib/study/storage.test.ts`, `frontend/src/components/content/markdown.test.tsx`

- [ ] **Bước 1: Viết test (sẽ fail)**

`src/lib/study/storage.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { lastLesson, readerSize, scrollPosition } from "./storage";

describe("study storage", () => {
  it("cỡ chữ mặc định 17 và luôn bị kẹp trong 15–21", () => {
    expect(readerSize.get()).toBe(17);
    readerSize.set(30);
    expect(readerSize.get()).toBe(21);
    readerSize.set(2);
    expect(readerSize.get()).toBe(15);
  });

  it("nhớ bài gần nhất theo từng khóa", () => {
    lastLesson.set("c1", "l9");
    expect(lastLesson.get("c1")).toBe("l9");
    expect(lastLesson.get("c2")).toBeNull();
  });

  it("dữ liệu hỏng thì trả giá trị mặc định thay vì ném lỗi", () => {
    localStorage.setItem("lms:scroll:l1", "{hỏng");
    expect(scrollPosition.get("l1")).toBe(0);
  });
});
```

`src/components/content/markdown.test.tsx`. Test này kiểm tra KaTeX, bảng GFM, và **không render HTML thô** (chống XSS):

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./markdown";

describe("Markdown", () => {
  it("render tiêu đề, bảng GFM và công thức KaTeX", () => {
    const { container } = render(<Markdown>{"## Đạo hàm\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n$x^2$"}</Markdown>);
    expect(screen.getByRole("heading", { name: "Đạo hàm" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("không render HTML thô", () => {
    const { container } = render(<Markdown>{'<img src=x onerror="alert(1)">'}</Markdown>);
    expect(container.querySelector("img")).toBeNull();
  });
});
```

Run: `npx vitest run src/lib/study src/components/content`
Expected: FAIL, lỗi `Failed to resolve import "./storage"` và `"./markdown"`.

- [ ] **Bước 2: Cài đặt phần lõi**

`src/lib/study/storage.ts`:

```ts
// Tiện ích lưu trên trình duyệt cho buổi học dài (design-system §8).
// Mọi truy cập localStorage đều bọc try/catch: chế độ ẩn danh có thể ném lỗi.

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // bỏ qua: chỉ là tiện ích
  }
}

export const READER_MIN = 15;
export const READER_MAX = 21;
export const READER_DEFAULT = 17;

export const readerSize = {
  get: () => Math.min(READER_MAX, Math.max(READER_MIN, read("lms:reader-size", READER_DEFAULT))),
  set: (px: number) => write("lms:reader-size", Math.min(READER_MAX, Math.max(READER_MIN, px))),
};

/** Bài học gần nhất của mỗi khóa → nút "Học tiếp". */
export const lastLesson = {
  get: (courseId: string) => read<string | null>(`lms:last-lesson:${courseId}`, null),
  set: (courseId: string, lessonId: string) => write(`lms:last-lesson:${courseId}`, lessonId),
};

/** Vị trí cuộn trong bài (tỉ lệ 0–1, không phụ thuộc cỡ chữ). */
export const scrollPosition = {
  get: (lessonId: string) => read<number>(`lms:scroll:${lessonId}`, 0),
  set: (lessonId: string, ratio: number) => write(`lms:scroll:${lessonId}`, Math.round(ratio * 1000) / 1000),
};

export type BreakPrefs = { enabled: boolean; snoozeUntil: number };
export const breakPrefs = {
  get: () => read<BreakPrefs>("lms:break", { enabled: true, snoozeUntil: 0 }),
  set: (p: BreakPrefs) => write("lms:break", p),
};
```

`src/components/content/markdown.tsx`:

```tsx
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { cn } from "@/lib/utils";

/**
 * Hiển thị markdown của bài học / câu trả lời AI. react-markdown không render HTML thô
 * (không có rehype-raw), nên nội dung không thể chèn <script>.
 */
export function Markdown({
  children,
  className,
  components,
}: {
  children: string;
  className?: string;
  components?: Components;
}) {
  return (
    <div className={cn("reader", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children: c, ...rest }) => (
            <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noreferrer" {...rest}>
              {c}
            </a>
          ),
          ...components,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
```

Run: `npx vitest run src/lib/study src/components/content`
Expected: PASS (5 test).

- [ ] **Bước 3: Truy vấn dữ liệu và tiện ích**

`src/lib/queries.ts` (query key tập trung ở `qk`, dùng lại ở mọi nơi):

```ts
"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type CourseDetail = components["schemas"]["CourseDetail"];
export type LessonDetail = components["schemas"]["LessonDetail"];

export const qk = {
  catalog: (q: string, page: number) => ["catalog", q, page] as const,
  course: (slug: string) => ["course", slug] as const,
  myCourses: (page: number) => ["my-courses", page] as const,
  lesson: (id: string) => ["lesson", id] as const,
  lessonVideo: (id: string) => ["lesson-video", id] as const,
  teacherCourses: (page: number) => ["teacher-courses", page] as const,
  sources: (lessonId: string) => ["sources", lessonId] as const,
  job: (id: string) => ["job", id] as const,
};

export function useCatalog(q: string, page: number) {
  return useQuery({
    queryKey: qk.catalog(q, page),
    queryFn: () =>
      unwrap(api.GET("/api/v1/courses", { params: { query: { q: q || undefined, page, size: 12 } } })),
    placeholderData: keepPreviousData,
  });
}

export function useCourse(slug: string) {
  return useQuery({
    queryKey: qk.course(slug),
    queryFn: () => unwrap(api.GET("/api/v1/courses/{slug}", { params: { path: { slug } } })),
  });
}

export function useMyCourses(page = 1, enabled = true) {
  return useQuery({
    queryKey: qk.myCourses(page),
    queryFn: () => unwrap(api.GET("/api/v1/me/courses", { params: { query: { page, size: 20 } } })),
    enabled,
  });
}

export function useLesson(id: string) {
  return useQuery({
    queryKey: qk.lesson(id),
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: id } } })),
  });
}

/** URL video đã ký (hết hạn sau 1 giờ). 404 = bài không có video → trả null. */
export function useLessonVideo(id: string) {
  return useQuery({
    queryKey: qk.lessonVideo(id),
    queryFn: async () => {
      try {
        const { url } = await unwrap(api.GET("/api/v1/lessons/{lesson_id}/video", { params: { path: { lesson_id: id } } }));
        return url;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    staleTime: 50 * 60_000,
  });
}

export function useEnroll(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (courseId: string) =>
      unwrap(api.POST("/api/v1/courses/{course_id}/enroll", { params: { path: { course_id: courseId } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.course(slug) });
      qc.invalidateQueries({ queryKey: ["my-courses"] });
    },
  });
}

export function useSaveProgress(lessonId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["ProgressIn"]) =>
      unwrap(api.PUT("/api/v1/lessons/{lesson_id}/progress", { params: { path: { lesson_id: lessonId } }, body })),
    onSuccess: (progress) => {
      qc.setQueryData<LessonDetail>(qk.lesson(lessonId), (old) => (old ? { ...old, progress } : old));
      if (progress.status === "done") qc.invalidateQueries({ queryKey: ["my-courses"] });
    },
  });
}

/** Danh sách bài học theo thứ tự (chương → bài) để tính bài trước/sau. */
export function flattenLessons(course: CourseDetail) {
  return [...course.sections]
    .sort((a, b) => a.position - b.position)
    .flatMap((s) => [...s.lessons].sort((a, b) => a.position - b.position).map((l) => ({ ...l, sectionTitle: s.title })));
}
```

`src/lib/use-debounced.ts`:

```ts
import * as React from "react";

export function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}
```

`src/lib/study/resume.ts`:

```ts
import type { CourseDetail } from "@/lib/queries";
import { flattenLessons } from "@/lib/queries";
import { lastLesson } from "./storage";

/** Bài để "Học tiếp": bài mở gần nhất trên máy này, không có thì bài đầu tiên. */
export function resumeLessonId(course: CourseDetail): string | null {
  const lessons = flattenLessons(course);
  const last = lastLesson.get(course.id);
  if (last && lessons.some((l) => l.id === last)) return last;
  return lessons[0]?.id ?? null;
}
```

- [ ] **Bước 4: Component khóa học**

`src/components/course/course-card.tsx`:

```tsx
import Link from "next/link";
import { Progress } from "@/components/ui/misc";

export function CourseCard({
  href,
  title,
  subtitle,
  description,
  progress,
}: {
  href: string;
  title: string;
  subtitle?: string;
  description?: string;
  progress?: { pct: number; done: number; total: number };
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-lg border bg-surface p-4 transition-colors duration-150 hover:border-primary/50"
    >
      <h2 className="font-semibold group-hover:text-primary">{title}</h2>
      {subtitle ? <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p> : null}
      {description ? <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{description}</p> : null}
      {progress ? (
        <div className="mt-auto pt-4">
          <Progress value={progress.pct} label={`Tiến độ ${title}`} />
          <p className="mt-1.5 text-xs text-muted-foreground">
            {progress.done}/{progress.total} bài · {progress.pct}%
          </p>
        </div>
      ) : null}
    </Link>
  );
}

export function Pagination({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Phân trang" className="mt-6 flex items-center justify-center gap-3 text-sm">
      <button className="h-10 rounded-md border px-3 disabled:opacity-50" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Trang trước
      </button>
      <span aria-current="page">
        {page}/{pages}
      </span>
      <button className="h-10 rounded-md border px-3 disabled:opacity-50" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Trang sau
      </button>
    </nav>
  );
}
```

`src/components/course/my-course-list.tsx`. Nếu trên máy này đã mở bài nào của khóa thì thẻ khóa dẫn **thẳng vào bài đó**:

```tsx
"use client";

import { BookMarked } from "lucide-react";
import Link from "next/link";
import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
import { CourseCard } from "@/components/course/course-card";
import { Button } from "@/components/ui/button";
import { useMyCourses } from "@/lib/queries";
import { lastLesson } from "@/lib/study/storage";

/** Có bài mở gần nhất trên máy này → vào thẳng bài đó; không thì mở trang khóa. */
function resumeHref(courseId: string, slug: string) {
  const last = lastLesson.get(courseId);
  return last ? `/learn/${slug}/${last}` : `/courses/${slug}`;
}

export function MyCourseList({ limit }: { limit?: number }) {
  const my = useMyCourses();
  if (my.isPending) return <CardListSkeleton count={limit ?? 3} />;
  if (my.isError) return <ErrorState error={my.error} onRetry={() => my.refetch()} />;
  if (my.data.items.length === 0)
    return (
      <EmptyState
        icon={BookMarked}
        title="Bạn chưa đăng ký khóa học nào."
        action={
          <Button asChild>
            <Link href="/explore">Khám phá khóa học</Link>
          </Button>
        }
      />
    );
  const items = limit ? my.data.items.slice(0, limit) : my.data.items;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((c) => (
        <CourseCard
          key={c.course_id}
          href={resumeHref(c.course_id, c.slug)}
          title={c.title}
          subtitle={c.completed_at ? "Đã hoàn thành" : undefined}
          progress={{ pct: c.progress_pct, done: c.done_lessons, total: c.total_lessons }}
        />
      ))}
    </div>
  );
}
```

- [ ] **Bước 5: Các trang**

`src/app/(main)/page.tsx` (trang chủ: khách thấy phần giới thiệu, học viên thấy "Tiếp tục học"):

```tsx
"use client";

import { ArrowRight, Compass } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/app/states";
import { MyCourseList } from "@/components/course/my-course-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { isStaff, useAuth } from "@/lib/auth/auth-context";

export default function HomePage() {
  const { user, status } = useAuth();
  if (status === "loading") return <Skeleton className="h-40 w-full" />;

  if (!user)
    return (
      <section className="mx-auto max-w-2xl py-10 text-center md:py-20">
        <h1 className="text-3xl font-semibold md:text-4xl">Học theo nhịp của bạn, có AI giải đáp ngay trong bài</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          AI Tutor trả lời dựa trên đúng tài liệu của khóa học và luôn ghi nguồn, để bạn kiểm chứng được.
        </p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/explore">
              <Compass /> Khám phá khóa học
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/register">Tạo tài khoản</Link>
          </Button>
        </div>
      </section>
    );

  return (
    <>
      <PageHeader title={`Chào ${user.full_name.split(" ").slice(-1)[0]}`}>
        {user.role === "student" ? "Tiếp tục từ chỗ bạn đã dừng." : "Quản lý các khóa bạn đang dạy."}
      </PageHeader>
      {user.role === "student" ? (
        <>
          <MyCourseList limit={3} />
          <Button asChild variant="link" className="mt-4">
            <Link href="/my">
              Xem tất cả khóa của tôi <ArrowRight />
            </Link>
          </Button>
        </>
      ) : (
        <Button asChild>
          <Link href={isStaff(user) ? "/teach" : "/explore"}>{isStaff(user) ? "Tới khóa đang dạy" : "Khám phá khóa học"}</Link>
        </Button>
      )}
    </>
  );
}
```

`src/app/(main)/explore/page.tsx` (tìm kiếm debounce 300ms, đổi từ khóa thì về trang 1):

```tsx
"use client";

import { Compass, Search } from "lucide-react";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { CourseCard, Pagination } from "@/components/course/course-card";
import { Input } from "@/components/ui/input";
import { useCatalog } from "@/lib/queries";
import { useDebounced } from "@/lib/use-debounced";

export default function ExplorePage() {
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  // đổi từ khóa thì quay về trang 1 (trang gắn với từ khóa đã tìm)
  const [paging, setPaging] = React.useState({ query: "", page: 1 });
  const page = paging.query === query ? paging.page : 1;
  const setPage = (p: number) => setPaging({ query, page: p });
  const catalog = useCatalog(query, page);

  return (
    <>
      <PageHeader title="Khám phá khóa học" />
      <div className="relative mb-6 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <label htmlFor="catalog-search" className="sr-only">
          Tìm khóa học
        </label>
        <Input
          id="catalog-search"
          type="search"
          placeholder="Tìm theo tên khóa học (có thể gõ không dấu)…"
          className="pl-9"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {catalog.isPending ? (
        <CardListSkeleton />
      ) : catalog.isError ? (
        <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} />
      ) : catalog.data.items.length === 0 ? (
        <EmptyState icon={Compass} title={query ? `Không tìm thấy khóa học nào cho “${query}”.` : "Chưa có khóa học nào được xuất bản."} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy={catalog.isFetching}>
            {catalog.data.items.map((c) => (
              <CourseCard key={c.id} href={`/courses/${c.slug}`} title={c.title} subtitle={c.teacher_name} description={c.description} />
            ))}
          </div>
          <Pagination page={page} total={catalog.data.total} size={catalog.data.size} onPage={setPage} />
        </>
      )}
    </>
  );
}
```

`src/app/(main)/courses/[slug]/page.tsx`:

- Nút chính đổi theo vai trò: Đăng ký / Học tiếp / Chỉnh sửa.
- Khách bấm Đăng ký thì sang `/login?next=…`.
- Trên điện thoại, hộp hành động dính phía trên thanh dưới.

```tsx
"use client";

import { BookOpenCheck, Clock, Pencil, PlayCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { Markdown } from "@/components/content/markdown";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { flattenLessons, useCourse, useEnroll } from "@/lib/queries";
import { resumeLessonId } from "@/lib/study/resume";

export default function CourseDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const course = useCourse(slug);
  const enroll = useEnroll(slug);

  if (course.isPending)
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Đang tải">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (course.isError) return <ErrorState error={course.error} onRetry={() => course.refetch()} />;

  const c = course.data;
  const lessons = flattenLessons(c);
  const totalMin = Math.round(lessons.reduce((s, l) => s + (l.duration_sec ?? 0), 0) / 60);
  const resumeId = resumeLessonId(c);
  const learnHref = resumeId ? `/learn/${c.slug}/${resumeId}` : null;

  async function onEnroll() {
    if (!user) return router.push(`/login?next=${encodeURIComponent(`/courses/${slug}`)}`);
    try {
      await enroll.mutateAsync(c.id);
      toast.success("Đã đăng ký khóa học");
      if (lessons[0]) router.push(`/learn/${c.slug}/${lessons[0].id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <div>
        {c.status !== "published" ? <Badge tone="accent" className="mb-3">Bản nháp — học viên chưa thấy</Badge> : null}
        <h1 className="text-2xl font-semibold md:text-3xl">{c.title}</h1>
        <p className="mt-2 text-muted-foreground">
          Giảng viên {c.teacher_name} · {lessons.length} bài{totalMin ? ` · khoảng ${totalMin} phút video` : ""}
        </p>
        {c.description ? <Markdown className="mt-6">{c.description}</Markdown> : null}

        <h2 className="mt-10 text-xl font-semibold">Nội dung khóa học</h2>
        <ol className="mt-4 space-y-4">
          {[...c.sections]
            .sort((a, b) => a.position - b.position)
            .map((s, i) => (
              <li key={s.id} className="rounded-lg border bg-surface">
                <h3 className="border-b px-4 py-3 font-medium">
                  Chương {i + 1}. {s.title}
                </h3>
                <ul>
                  {[...s.lessons]
                    .sort((a, b) => a.position - b.position)
                    .map((l) => (
                      <li key={l.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                        {c.is_enrolled || c.is_owner ? (
                          <Link href={`/learn/${c.slug}/${l.id}`} className="hover:text-primary hover:underline">
                            {l.title}
                          </Link>
                        ) : (
                          <span>{l.title}</span>
                        )}
                        {l.duration_sec ? (
                          <span className="flex shrink-0 items-center gap-1 text-muted-foreground">
                            <Clock className="size-3.5" aria-hidden />
                            {Math.ceil(l.duration_sec / 60)} phút
                          </span>
                        ) : null}
                      </li>
                    ))}
                </ul>
              </li>
            ))}
        </ol>
      </div>

      {/* Hộp hành động: dính bên phải trên desktop, dính đáy trên điện thoại */}
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className="fixed inset-x-0 bottom-16 z-20 border-t bg-surface p-3 md:static md:rounded-lg md:border md:p-5">
          {c.is_owner ? (
            <Button asChild size="lg" className="w-full">
              <Link href={`/teach/${c.slug}`}>
                <Pencil /> Chỉnh sửa khóa học
              </Link>
            </Button>
          ) : c.is_enrolled ? (
            learnHref ? (
              <Button asChild size="lg" className="w-full">
                <Link href={learnHref}>
                  <PlayCircle /> Học tiếp
                </Link>
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">Khóa học chưa có bài nào.</p>
            )
          ) : user && user.role !== "student" ? (
            <p className="text-sm text-muted-foreground">Chỉ tài khoản học viên mới đăng ký được khóa học.</p>
          ) : (
            <Button size="lg" className="w-full" onClick={onEnroll} loading={enroll.isPending} loadingText="Đang đăng ký…">
              <BookOpenCheck /> Đăng ký khóa học
            </Button>
          )}
        </div>
      </aside>
    </div>
  );
}
```

`src/app/(main)/my/page.tsx`:

```tsx
"use client";

import { PageHeader } from "@/components/app/states";
import { MyCourseList } from "@/components/course/my-course-list";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function MyCoursesPage() {
  return (
    <RequireAuth>
      <PageHeader title="Khóa của tôi" />
      <MyCourseList />
    </RequireAuth>
  );
}
```

`src/app/(main)/account/page.tsx`. Trên điện thoại không có menu góc trên, nên đây là nơi đổi chế độ màu và đăng xuất:

```tsx
"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/app/states";
import { ThemeSwitcher } from "@/components/app/theme-switcher";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";
import { RequireAuth } from "@/lib/auth/require-auth";

const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

/** Trang tài khoản (chủ yếu cho điện thoại, nơi không có menu góc trên). */
export default function AccountPage() {
  const { user, logout } = useAuth();
  const router = useRouter();
  return (
    <RequireAuth>
      <PageHeader title="Tài khoản" />
      {user ? (
        <div className="max-w-md space-y-8">
          <div>
            <p className="font-medium">{user.full_name}</p>
            <p className="text-sm text-muted-foreground">
              {user.email} · {ROLE_LABEL[user.role]}
            </p>
          </div>
          <div>
            <h2 className="mb-2 text-sm font-medium">Chế độ màu</h2>
            <ThemeSwitcher />
          </div>
          <Button
            variant="outline"
            onClick={async () => {
              await logout();
              router.push("/");
            }}
          >
            <LogOut /> Đăng xuất
          </Button>
        </div>
      ) : null}
    </RequireAuth>
  );
}
```

- [ ] **Bước 6: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test && npm run build
git add frontend/src && git commit -m "feat(web): catalog, course detail, my courses and home"
```

Expected: test PASS. Build liệt kê `○ /`, `○ /explore`, `ƒ /courses/[slug]`, `○ /my`, `○ /account`.

---

## Task 11: Tiện ích cho buổi học dài: nhắc nghỉ mắt, phím tắt, tự lưu

**Files:**
- Create: `frontend/src/lib/study/use-break-reminder.ts`, `frontend/src/lib/study/use-shortcuts.ts`, `frontend/src/lib/use-autosave.ts`
- Test: `frontend/src/lib/study/use-break-reminder.test.ts`, `frontend/src/lib/study/use-shortcuts.test.tsx`, `frontend/src/lib/use-autosave.test.ts`

Quy tắc theo design-system §8:

- **Nhắc nghỉ mắt:** chỉ đếm khi tab đang hiển thị và có tương tác. Rời máy quá 5 phút thì đếm lại từ đầu. Không nhắc khi `paused` (quiz có giờ ở FE-2).
- **Tự lưu:** các lần lưu chạy **tuần tự**, không bao giờ gửi 2 request song song, và không để bản cũ ghi đè bản mới.

- [ ] **Bước 1: Viết test (sẽ fail)**

`src/lib/study/use-break-reminder.test.ts`:

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { breakPrefs } from "./storage";
import { useBreakReminder } from "./use-break-reminder";

function study(minutes: number) {
  // mỗi 30 giây có một tương tác, giống người đang đọc và cuộn
  for (let i = 0; i < minutes * 2; i++) {
    act(() => {
      window.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(30_000);
    });
  }
}

describe("useBreakReminder", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("nhắc sau 45 phút học liên tục", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(44);
    expect(result.current.due).toBe(false);
    study(1.5);
    expect(result.current.due).toBe(true);
  });

  it("không nhắc khi đang làm quiz (paused)", () => {
    const { result } = renderHook(() => useBreakReminder({ paused: true }));
    study(60);
    expect(result.current.due).toBe(false);
  });

  it("rời máy hơn 5 phút thì đếm lại từ đầu", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(40);
    act(() => {
      vi.advanceTimersByTime(6 * 60_000); // không có tương tác
    });
    study(10);
    expect(result.current.due).toBe(false);
  });

  it("Tắt nhắc thì lưu lại và không nhắc nữa", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(46);
    act(() => result.current.disable());
    expect(result.current.due).toBe(false);
    expect(breakPrefs.get().enabled).toBe(false);
  });
});
```

`src/lib/study/use-shortcuts.test.tsx`:

```tsx
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useShortcuts } from "./use-shortcuts";

function Harness({ onF }: { onF: () => void }) {
  useShortcuts({ f: onF });
  return <input aria-label="ô nhập" />;
}

describe("useShortcuts", () => {
  it("gọi handler khi bấm phím ngoài ô nhập (không phân biệt hoa thường)", () => {
    const onF = vi.fn();
    render(<Harness onF={onF} />);
    fireEvent.keyDown(window, { key: "F" });
    expect(onF).toHaveBeenCalledTimes(1);
  });

  it("bỏ qua khi đang gõ trong ô nhập hoặc có Ctrl", () => {
    const onF = vi.fn();
    const { getByLabelText } = render(<Harness onF={onF} />);
    fireEvent.keyDown(getByLabelText("ô nhập"), { key: "f" });
    fireEvent.keyDown(window, { key: "f", ctrlKey: true });
    expect(onF).not.toHaveBeenCalled();
  });
});
```

`src/lib/use-autosave.test.ts`:

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAutosave } from "./use-autosave";

describe("useAutosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("lưu một lần sau khi ngừng gõ 1 giây", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { rerender, result } = renderHook(({ v }) => useAutosave(v, save), { initialProps: { v: "a" } });
    rerender({ v: "ab" });
    rerender({ v: "abc" });
    expect(result.current.state.status).toBe("dirty");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("abc");
    expect(result.current.state.status).toBe("saved");
  });

  it("đang lưu mà gõ tiếp: không gửi song song, lưu bản mới nhất sau", async () => {
    let resolveFirst!: () => void;
    const calls: string[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const save = vi.fn((v: string) => {
      calls.push(v);
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      return new Promise<void>((r) => {
        const done = () => {
          inFlight--;
          r();
        };
        if (calls.length === 1) resolveFirst = done;
        else done();
      });
    });
    const { rerender } = renderHook(({ v }) => useAutosave(v, save), { initialProps: { v: "x" } });
    rerender({ v: "x1" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    rerender({ v: "x12" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(calls).toEqual(["x1"]); // lần 2 đang đợi lần 1
    await act(async () => {
      resolveFirst();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(calls).toEqual(["x1", "x12"]);
    expect(maxInFlight).toBe(1);
  });

  it("lỗi thì báo trạng thái error", async () => {
    const save = vi.fn().mockRejectedValue(new Error("Mất mạng"));
    const { rerender, result } = renderHook(({ v }) => useAutosave(v, save), { initialProps: { v: 1 } });
    rerender({ v: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.state).toEqual({ status: "error", message: "Mất mạng" });
  });
});
```

Run: `npx vitest run src/lib/study src/lib/use-autosave.test.ts`
Expected: FAIL, lỗi `Failed to resolve import "./use-break-reminder"`, `"./use-shortcuts"`, `"./use-autosave"`.

- [ ] **Bước 2: Cài đặt**

`src/lib/study/use-break-reminder.ts`:

```ts
"use client";

import * as React from "react";
import { breakPrefs } from "./storage";

export const BREAK_AFTER_MS = 45 * 60_000;
export const SNOOZE_MS = 15 * 60_000;
const IDLE_RESET_MS = 5 * 60_000; // rời máy > 5 phút coi như đã nghỉ

/**
 * Nhắc nghỉ mắt sau 45 phút học liên tục (design-system §8).
 * Chỉ đếm khi tab đang hiển thị; tạm dừng khi `paused` (vd. đang làm quiz có giờ).
 */
export function useBreakReminder({ paused = false }: { paused?: boolean } = {}) {
  const [due, setDue] = React.useState(false);
  // hook chỉ chạy trong trang client-only (sau RequireAuth) nên đọc localStorage lúc khởi tạo được
  const [enabled, setEnabled] = React.useState(() => breakPrefs.get().enabled);
  const activeMs = React.useRef(0);
  const lastTick = React.useRef(0);
  const lastActivity = React.useRef(0);

  React.useEffect(() => {
    lastActivity.current = Date.now();
    const mark = () => {
      lastActivity.current = Date.now();
    };
    const events = ["pointerdown", "keydown", "scroll", "wheel"] as const;
    events.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    return () => events.forEach((e) => window.removeEventListener(e, mark));
  }, []);

  React.useEffect(() => {
    if (!enabled || paused) return;
    lastTick.current = Date.now();
    const id = window.setInterval(() => {
      const now = Date.now();
      const delta = now - lastTick.current;
      lastTick.current = now;
      if (document.visibilityState !== "visible") return;
      if (now - lastActivity.current > IDLE_RESET_MS) {
        activeMs.current = 0;
        return;
      }
      activeMs.current += delta;
      if (activeMs.current >= BREAK_AFTER_MS && now >= breakPrefs.get().snoozeUntil) setDue(true);
    }, 30_000);
    return () => window.clearInterval(id);
  }, [enabled, paused]);

  const done = React.useCallback(() => {
    activeMs.current = 0;
    setDue(false);
  }, []);
  const snooze = React.useCallback(() => {
    breakPrefs.set({ ...breakPrefs.get(), snoozeUntil: Date.now() + SNOOZE_MS });
    activeMs.current = 0;
    setDue(false);
  }, []);
  const disable = React.useCallback(() => {
    breakPrefs.set({ ...breakPrefs.get(), enabled: false });
    setEnabled(false);
    setDue(false);
  }, []);

  return { due: due && enabled && !paused, done, snooze, disable };
}
```

`src/lib/study/use-shortcuts.ts`:

```ts
"use client";

import * as React from "react";

export type ShortcutMap = Record<string, (e: KeyboardEvent) => void>;

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

/**
 * Phím tắt một phím (design-system §8): "/", "f", "ArrowLeft", "ArrowRight", "Escape", "?".
 * Bỏ qua khi đang gõ trong ô nhập (trừ Escape) hoặc khi có Ctrl/Alt/Meta.
 */
export function useShortcuts(map: ShortcutMap, enabled = true) {
  const ref = React.useRef(map);
  React.useEffect(() => {
    ref.current = map;
  });
  React.useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey || e.defaultPrevented) return;
      if (e.key !== "Escape" && isTyping(e.target)) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const handler = ref.current[key];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
```

`src/lib/use-autosave.ts`:

```ts
"use client";

import * as React from "react";

export type AutosaveState =
  | { status: "idle" }
  | { status: "dirty" }
  | { status: "saving" }
  | { status: "saved"; at: Date }
  | { status: "error"; message: string };

/**
 * Tự lưu sau khi ngừng gõ `delay` ms. Các lần lưu chạy TUẦN TỰ: nếu đang lưu mà có thay đổi mới,
 * đợi lần lưu hiện tại xong rồi lưu bản mới nhất (không bao giờ ghi đè bản mới bằng bản cũ).
 * `flush()` lưu ngay (nút "Lưu", rời trang).
 */
export function useAutosave<T>(value: T, save: (v: T) => Promise<unknown>, { delay = 1000, enabled = true } = {}) {
  const [state, setState] = React.useState<AutosaveState>({ status: "idle" });
  const latest = React.useRef(value);
  const saved = React.useRef(value);
  const saveRef = React.useRef(save);
  const running = React.useRef<Promise<void> | null>(null);
  const timer = React.useRef<number | undefined>(undefined);

  React.useEffect(() => {
    saveRef.current = save;
  });

  // Một vòng lặp duy nhất: lưu bản mới nhất cho tới khi khớp với bản đã lưu, rồi dừng.
  const run = React.useCallback((): Promise<void> => {
    if (running.current) return running.current; // vòng đang chạy sẽ tự lấy bản mới nhất
    running.current = (async () => {
      while (!Object.is(latest.current, saved.current)) {
        const v = latest.current;
        setState({ status: "saving" });
        try {
          await saveRef.current(v);
          saved.current = v;
        } catch (err) {
          setState({ status: "error", message: err instanceof Error ? err.message : "Không lưu được" });
          return;
        }
      }
      setState({ status: "saved", at: new Date() });
    })().finally(() => {
      running.current = null;
    });
    return running.current;
  }, []);

  React.useEffect(() => {
    latest.current = value;
    if (!enabled || Object.is(value, saved.current)) return;
    setState({ status: "dirty" });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void run(), delay);
    return () => window.clearTimeout(timer.current);
  }, [value, delay, enabled, run]);

  /** Đặt lại mốc "đã lưu" khi tải dữ liệu mới từ server (đổi bài). */
  const reset = React.useCallback((v: T) => {
    latest.current = v;
    saved.current = v;
    setState({ status: "idle" });
  }, []);

  const flush = React.useCallback(() => {
    window.clearTimeout(timer.current);
    return run();
  }, [run]);

  return { state, flush, reset };
}

export function autosaveLabel(s: AutosaveState) {
  switch (s.status) {
    case "dirty":
      return "Chưa lưu";
    case "saving":
      return "Đang lưu…";
    case "saved":
      return `Đã lưu lúc ${s.at.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
    case "error":
      return `Lưu thất bại: ${s.message}`;
    default:
      return "";
  }
}
```

- [ ] **Bước 3: Chạy, xác nhận pass**

Run: `npx vitest run src/lib/study src/lib/use-autosave.test.ts`
Expected: PASS (12 test: 4 test nhắc nghỉ, 2 test phím tắt, 3 test tự lưu, 3 test storage đã có từ Task 10).

> Nếu test autosave bị treo hoặc worker bị SIGKILL thì có vòng lặp vô hạn. Kiểm tra lại: vòng `while` trong `run()` phải `return` ngay khi lưu lỗi.

- [ ] **Bước 4: Commit**

```bash
git add frontend/src/lib && git commit -m "feat(web): break reminder, keyboard shortcuts and sequential autosave"
```

---

## Task 12: AI Tutor: hook hội thoại SSE và panel chat

**Files:**
- Create: `frontend/src/lib/tutor/types.ts`, `citations.ts`, `use-tutor-chat.ts`, `frontend/src/components/tutor/citation-chip.tsx`, `tutor-panel.tsx`
- Test: `frontend/src/lib/tutor/citations.test.ts`, `frontend/src/lib/tutor/use-tutor-chat.test.tsx`

Hành vi theo design-system §5.3 (AI Tutor):

- Nguồn hiện **trước** câu trả lời ("Đã tìm thấy N đoạn…"). Chữ hiện dần.
- Nút Gửi đổi thành **Dừng** trong lúc AI đang trả lời.
- `[n]` biến thành chip bấm được. Chip mở thẻ nguồn gồm đoạn trích, bài, trang hoặc phút, kèm "Tua tới mm:ss" nếu nguồn là video của bài đang mở.
- 👍/👎 có `aria-pressed`.
- Gặp 429 thì nút Gửi đếm ngược theo `Retry-After`.

> **Lệch so với design-system:** design ghi "bấm nguồn → cuộn tới đúng đoạn trong bài". Thực tế nguồn RAG là các đoạn của **file PDF** (không phải nội dung markdown của bài), và học viên không có trang xem PDF. Vì vậy chip mở **thẻ trích dẫn** thay cho việc cuộn. Với nguồn video thì có nút tua.

- [ ] **Bước 1: Viết test (sẽ fail)**

`src/lib/tutor/citations.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatTimestamp, linkCitations } from "./citations";

describe("linkCitations", () => {
  it("đổi [n] hợp lệ thành link, giữ nguyên số không có trong nguồn", () => {
    expect(linkCitations("Theo [1] và [3].", new Set([1, 2]))).toBe("Theo [1](#cite-1) và [3].");
  });
  it("không đụng vào code", () => {
    expect(linkCitations("`a[1]` và [1]", new Set([1]))).toBe("`a[1]` và [1](#cite-1)");
  });
  it("không đổi link markdown có sẵn", () => {
    expect(linkCitations("[1](http://x)", new Set([1]))).toBe("[1](http://x)");
  });
});

describe("formatTimestamp", () => {
  it("phút:giây và giờ:phút:giây", () => {
    expect(formatTimestamp(75.4)).toBe("1:15");
    expect(formatTimestamp(3725)).toBe("1:02:05");
  });
});
```

`src/lib/tutor/use-tutor-chat.test.tsx`. Test này giả lập stream SSE bằng MSW, gồm 3 tình huống: stream thành công, `error` là event đầu tiên, và 429:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it } from "vitest";
import { api, server } from "@/test/msw";
import { useTutorChat } from "./use-tutor-chat";

function sse(events: [string, unknown][]) {
  const body = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
  return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
}

function setup() {
  server.use(
    http.get(api("/tutor/availability"), () => HttpResponse.json({ available: true, ready_chunks: 5, message: null })),
    http.get(api("/tutor/sessions"), () => HttpResponse.json({ items: [], total: 0, page: 1, size: 20 })),
    http.post(api("/tutor/sessions"), () =>
      HttpResponse.json({ id: "s1", course_id: "c1", lesson_id: "l1", created_at: "2026-10-01T00:00:00Z" }, { status: 201 }),
    ),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper });
}

const source = { n: 1, chunk_id: "k1", lesson_id: "l1", page_no: 3, start_sec: null, lesson_title: "Bài 1", heading_path: "Đạo hàm", snippet: "..." };

describe("useTutorChat", () => {
  it("stream: nguồn hiện trước, token nối dần, done thay bằng nội dung cuối", async () => {
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () =>
        sse([
          ["sources", { sources: [source] }],
          ["token", { text: "Đạo hàm là " }],
          ["token", { text: "giới hạn [1]" }],
          ["done", { message_id: "m9", content: "Đạo hàm là giới hạn [1].", citations: [source], refused: false }],
        ]),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    await act(() => result.current.send("Đạo hàm là gì?"));
    const [q, a] = result.current.messages;
    expect(q).toMatchObject({ role: "user", content: "Đạo hàm là gì?" });
    expect(a).toMatchObject({ id: "m9", status: "done", content: "Đạo hàm là giới hạn [1]." });
    expect(a.sources).toHaveLength(1);
  });

  it("event error (kể cả là event đầu tiên) → trạng thái lỗi kèm câu dễ hiểu", async () => {
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () =>
        sse([["error", { code: "AI_UNAVAILABLE", message: "AI đang bận" }]]),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    await act(() => result.current.send("Hỏi"));
    expect(result.current.messages[1]).toMatchObject({ status: "error", error: "AI đang bận" });
    expect(result.current.busy).toBe(false);
  });

  it("429 trước khi stream → lỗi + mốc thời gian được hỏi lại", async () => {
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () =>
        HttpResponse.json(
          { error: { code: "RATE_LIMITED", message: "Chậm lại", details: {}, request_id: null } },
          { status: 429, headers: { "Retry-After": "40" } },
        ),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    await act(() => result.current.send("Hỏi"));
    expect(result.current.messages[1].error).toMatch(/40 giây/);
    expect(result.current.retryAt).toBeGreaterThan(Date.now());
  });
});
```

Run: `npx vitest run src/lib/tutor`
Expected: FAIL, lỗi `Failed to resolve import "./citations"` và `"./use-tutor-chat"`.

- [ ] **Bước 2: Cài đặt**

`src/lib/tutor/types.ts`:

```ts
import type { components } from "@/lib/api/schema";

export type Citation = components["schemas"]["Citation"];

/** Một nguồn trong event `sources` (có thêm phần hiển thị so với Citation). */
export type Source = Citation & { lesson_title: string; heading_path: string; snippet: string };

export type ChatStatus = "streaming" | "done" | "error" | "stopped";

export type ChatMessage = {
  id: string; // id tạm "local-…" cho tới khi nhận `done`
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  sources: Source[];
  refused: boolean;
  truncated: boolean;
  feedback: number | null;
  status: ChatStatus;
  error?: string;
};
```

`src/lib/tutor/citations.ts`:

````ts
/**
 * Đổi các dấu [n] trong câu trả lời thành link markdown [n](#cite-n) để render thành chip.
 * Chỉ đổi khi n có trong danh sách nguồn; bỏ qua phần trong code (`...` và ```...```).
 */
export function linkCitations(text: string, validNumbers: Set<number>): string {
  const parts = text.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  return parts
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(/\[(\d{1,2})\](?!\()/g, (m, n) => (validNumbers.has(Number(n)) ? `[${n}](#cite-${n})` : m)),
    )
    .join("");
}

export function formatTimestamp(sec: number) {
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}
````

`src/lib/tutor/use-tutor-chat.ts`:

```ts
"use client";

import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { api, apiBase, authFetch, unwrap } from "@/lib/api/client";
import { ApiError, errorMessage, toApiError } from "@/lib/api/errors";
import { readSse } from "@/lib/api/sse";
import type { ChatMessage, Citation, Source } from "./types";

type Scope = { courseId: string; lessonId: string | null };

const AI_ERROR = "AI Tutor tạm thời không trả lời được. Câu hỏi của bạn đã được lưu, bấm Thử lại sau ít phút.";

function fromServer(m: {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  refused: boolean;
  truncated: boolean;
  feedback: number | null;
}): ChatMessage {
  return { ...m, sources: [], status: m.truncated ? "stopped" : "done" };
}

/**
 * Hội thoại AI Tutor của một bài (hoặc cả khóa khi lessonId = null).
 * - Dùng lại phiên gần nhất cùng phạm vi; chưa có thì tạo khi gửi câu đầu.
 * - Trả lời stream qua SSE: sources → token… → done | error (error có thể là event đầu).
 * - Nội dung cuối lấy từ done.content (token stream có thể còn [n] thô / phần bị lọc).
 */
export function useTutorChat({ courseId, lessonId }: Scope, enabled = true) {
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [retryAt, setRetryAt] = React.useState<number | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  const availability = useQuery({
    queryKey: ["tutor-availability", courseId, lessonId],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/tutor/availability", {
          params: { query: { course_id: courseId, lesson_id: lessonId ?? undefined } },
        }),
      ),
    enabled,
  });

  const history = useQuery({
    queryKey: ["tutor-history", courseId, lessonId],
    enabled,
    staleTime: Infinity, // sau lần tải đầu, state cục bộ là nguồn chính
    gcTime: 0,
    queryFn: async () => {
      const sessions = await unwrap(
        api.GET("/api/v1/tutor/sessions", { params: { query: { course_id: courseId, size: 20 } } }),
      );
      const session = sessions.items.find((s) => (s.lesson_id ?? null) === lessonId);
      if (!session) return { sessionId: null, messages: [] as ChatMessage[] };
      const page = await unwrap(
        api.GET("/api/v1/tutor/sessions/{session_id}/messages", {
          params: { path: { session_id: session.id }, query: { size: 100 } },
        }),
      );
      return { sessionId: session.id, messages: page.items.map(fromServer) };
    },
  });

  React.useEffect(() => {
    if (history.data) {
      setSessionId(history.data.sessionId);
      setMessages(history.data.messages);
    }
  }, [history.data]);

  const patchLast = (fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((ms) => (ms.length ? [...ms.slice(0, -1), fn(ms[ms.length - 1])] : ms));

  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const s = await unwrap(
      api.POST("/api/v1/tutor/sessions", { body: { course_id: courseId, lesson_id: lessonId } }),
    );
    setSessionId(s.id);
    return s.id;
  };

  const send = React.useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text || busy) return;
      setBusy(true);
      const now = Date.now();
      setMessages((ms) => [
        ...ms,
        { id: `local-u-${now}`, role: "user", content: text, citations: [], sources: [], refused: false, truncated: false, feedback: null, status: "done" },
        { id: `local-a-${now}`, role: "assistant", content: "", citations: [], sources: [], refused: false, truncated: false, feedback: null, status: "streaming" },
      ]);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const sid = await ensureSession();
        const res = await authFetch(
          new Request(`${apiBase()}/api/v1/tutor/sessions/${sid}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify({ content: text }),
            signal: controller.signal,
          }),
        );
        if (!res.ok || !res.body) throw await toApiError(res);
        let gotDone = false;
        for await (const ev of readSse(res.body, controller.signal)) {
          const data = JSON.parse(ev.data);
          if (ev.event === "sources") patchLast((m) => ({ ...m, sources: data.sources as Source[] }));
          else if (ev.event === "token") patchLast((m) => ({ ...m, content: m.content + data.text }));
          else if (ev.event === "done") {
            gotDone = true;
            patchLast((m) => ({
              ...m,
              id: data.message_id,
              content: data.content,
              citations: data.citations,
              refused: data.refused,
              status: "done",
            }));
          } else if (ev.event === "error") {
            gotDone = true;
            patchLast((m) => ({ ...m, status: "error", truncated: true, error: data.message || AI_ERROR }));
          }
        }
        if (!gotDone && !controller.signal.aborted)
          patchLast((m) => ({ ...m, status: "error", truncated: true, error: "Mất kết nối giữa chừng. " + AI_ERROR }));
      } catch (err) {
        if (controller.signal.aborted) {
          patchLast((m) => ({ ...m, status: "stopped", truncated: true }));
        } else {
          if (err instanceof ApiError && err.status === 429 && err.retryAfter) setRetryAt(Date.now() + err.retryAfter * 1000);
          // lỗi trước khi stream mở (429, 403...): bỏ bong bóng trả lời rỗng, báo lỗi ở đó
          patchLast((m) => ({ ...m, status: "error", error: errorMessage(err) }));
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [busy, sessionId, courseId, lessonId],
  );

  const clearRetry = React.useCallback(() => setRetryAt(null), []);
  const stop = React.useCallback(() => abortRef.current?.abort(), []);

  /** Gửi lại câu hỏi gần nhất (câu cũ đã được lưu phía server nên lịch sử sẽ có 2 lần hỏi). */
  const retry = React.useCallback(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages((ms) => ms.slice(0, -2));
    void send(lastUser.content);
  }, [messages, send]);

  const feedback = React.useCallback(async (messageId: string, value: 1 | -1 | null) => {
    setMessages((ms) => ms.map((m) => (m.id === messageId ? { ...m, feedback: value } : m)));
    await unwrap(
      api.POST("/api/v1/tutor/messages/{message_id}/feedback", { params: { path: { message_id: messageId } }, body: { value } }),
    );
  }, []);

  return {
    availability: availability.data,
    loadingHistory: history.isLoading,
    historyError: history.error,
    messages,
    busy,
    retryAt,
    clearRetry,
    send,
    stop,
    retry,
    feedback,
  };
}
```

- [ ] **Bước 3: Chạy, xác nhận pass**

Run: `npx vitest run src/lib/tutor`
Expected: PASS (7 test).

- [ ] **Bước 4: Giao diện**

`src/components/tutor/citation-chip.tsx`:

```tsx
"use client";

import { Popover } from "radix-ui";
import { formatTimestamp } from "@/lib/tutor/citations";
import type { Citation, Source } from "@/lib/tutor/types";
import { Button } from "@/components/ui/button";

/**
 * Chip [n] trong câu trả lời. Bấm mở thẻ nhỏ: đoạn trích, bài, trang/giây.
 * Nếu nguồn là video của bài đang mở → nút "Tua tới mm:ss".
 */
export function CitationChip({
  n,
  citation,
  source,
  currentLessonId,
  onSeek,
  onOpenLesson,
}: {
  n: number;
  citation?: Citation;
  source?: Source;
  currentLessonId: string | null;
  onSeek?: (sec: number) => void;
  onOpenLesson?: (lessonId: string) => void;
}) {
  const c = source ?? citation;
  const where = c?.start_sec != null ? `phút ${formatTimestamp(c.start_sec)}` : c?.page_no != null ? `trang ${c.page_no}` : null;
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`Nguồn ${n}${where ? `, ${where}` : ""}`}
          className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border border-accent/50 px-1 align-text-top text-xs font-medium text-accent hover:bg-accent/10"
        >
          {n}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content sideOffset={6} className="z-50 w-72 rounded-md border bg-surface p-3 text-sm shadow-md">
          <p className="font-medium">
            [{n}] {source?.lesson_title ?? "Tài liệu bài học"}
            {where ? <span className="font-normal text-muted-foreground"> · {where}</span> : null}
          </p>
          {source?.heading_path ? <p className="mt-0.5 text-xs text-muted-foreground">{source.heading_path}</p> : null}
          {source?.snippet ? <p className="mt-2 line-clamp-5 text-muted-foreground">{source.snippet}</p> : null}
          <div className="mt-3 flex gap-2">
            {c?.start_sec != null && c.lesson_id === currentLessonId && onSeek ? (
              <Button size="sm" variant="outline" onClick={() => onSeek(c.start_sec!)}>
                Tua tới {formatTimestamp(c.start_sec)}
              </Button>
            ) : null}
            {c && c.lesson_id !== currentLessonId && onOpenLesson ? (
              <Button size="sm" variant="outline" onClick={() => onOpenLesson(c.lesson_id)}>
                Mở bài này
              </Button>
            ) : null}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
```

`src/components/tutor/tutor-panel.tsx`:

- Enter để gửi, Shift+Enter để xuống dòng. Có kiểm tra `isComposing` để không gửi nhầm khi đang gõ dấu bằng bộ gõ tiếng Việt (IME).
- Panel tự cuộn xuống khi có chữ mới, **trừ khi** người dùng đang cuộn lên đọc lại.

```tsx
"use client";

import { MessageCircleQuestion, RotateCcw, SendHorizontal, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Markdown } from "@/components/content/markdown";
import { Button } from "@/components/ui/button";
import { Skeleton, Tip } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { linkCitations } from "@/lib/tutor/citations";
import type { ChatMessage } from "@/lib/tutor/types";
import type { useTutorChat } from "@/lib/tutor/use-tutor-chat";
import { cn } from "@/lib/utils";
import { CitationChip } from "./citation-chip";

type Chat = ReturnType<typeof useTutorChat>;

/** Nội dung panel AI Tutor (dùng chung cho cột phải desktop và khung trượt điện thoại). */
export function TutorPanel({
  chat,
  lessonId,
  onSeek,
  onOpenLesson,
}: {
  chat: Chat;
  lessonId: string | null;
  onSeek?: (sec: number) => void;
  onOpenLesson?: (lessonId: string) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const listRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const countdown = useCountdown(chat.retryAt, chat.clearRetry);
  const unavailable = chat.availability && !chat.availability.available;

  React.useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // tự cuộn xuống khi có chữ mới, trừ khi người dùng đang cuộn lên đọc lại
  const last = chat.messages[chat.messages.length - 1];
  React.useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [last?.content, chat.messages.length]);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!draft.trim() || chat.busy || countdown > 0) return;
    void chat.send(draft);
    setDraft("");
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={listRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite" aria-busy={chat.busy}>
        {chat.loadingHistory ? (
          <div className="space-y-3" aria-label="Đang tải hội thoại">
            <Skeleton className="ml-auto h-10 w-2/3" />
            <Skeleton className="h-20 w-5/6" />
          </div>
        ) : chat.messages.length === 0 ? (
          <div className="flex flex-col items-center gap-2 pt-10 text-center text-muted-foreground">
            <MessageCircleQuestion className="size-8" aria-hidden />
            <p>Hỏi bất cứ điều gì về bài này. AI chỉ trả lời dựa trên tài liệu của khóa và ghi rõ nguồn.</p>
          </div>
        ) : (
          chat.messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="ml-auto max-w-[85%] rounded-lg bg-muted px-3 py-2 whitespace-pre-wrap">
                {m.content}
              </div>
            ) : (
              <AssistantMessage
                key={m.id}
                m={m}
                lessonId={lessonId}
                onSeek={onSeek}
                onOpenLesson={onOpenLesson}
                onRetry={chat.retry}
                onFeedback={async (v) => {
                  try {
                    await chat.feedback(m.id, v);
                    if (v !== null) toast("Cảm ơn góp ý của bạn");
                  } catch (err) {
                    toast.error(errorMessage(err));
                  }
                }}
              />
            ),
          )
        )}
      </div>

      <form onSubmit={submit} className="border-t p-3">
        {unavailable ? (
          <p className="mb-2 text-sm text-muted-foreground">{chat.availability?.message ?? "AI Tutor chưa sẵn sàng cho bài này."}</p>
        ) : null}
        <div className="flex items-end gap-2">
          <label htmlFor="tutor-input" className="sr-only">
            Câu hỏi cho AI Tutor
          </label>
          <textarea
            id="tutor-input"
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) submit(e);
            }}
            rows={2}
            maxLength={2000}
            disabled={!!unavailable}
            placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
            className="max-h-40 min-h-11 flex-1 resize-none rounded-md border bg-surface px-3 py-2 text-base md:text-sm"
          />
          {chat.busy ? (
            <Button type="button" variant="outline" onClick={chat.stop}>
              <Square /> Dừng
            </Button>
          ) : (
            <Button type="submit" disabled={!draft.trim() || countdown > 0 || !!unavailable}>
              <SendHorizontal /> {countdown > 0 ? `${countdown}s` : "Gửi"}
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

function AssistantMessage({
  m,
  lessonId,
  onSeek,
  onOpenLesson,
  onRetry,
  onFeedback,
}: {
  m: ChatMessage;
  lessonId: string | null;
  onSeek?: (sec: number) => void;
  onOpenLesson?: (id: string) => void;
  onRetry: () => void;
  onFeedback: (v: 1 | -1 | null) => void;
}) {
  const numbers = new Set([...m.sources.map((s) => s.n), ...m.citations.map((c) => c.n)]);
  const body = linkCitations(m.content, numbers);
  return (
    <div className="max-w-[95%]">
      {m.sources.length > 0 && m.status === "streaming" ? (
        <p className="mb-1 text-xs text-muted-foreground">Đã tìm thấy {m.sources.length} đoạn tài liệu liên quan…</p>
      ) : null}
      {m.content ? (
        <Markdown
          className={cn("text-[15px] [--reader-size:15px]", m.refused && "text-muted-foreground")}
          components={{
            a: ({ href, children }) => {
              const match = href?.match(/^#cite-(\d+)$/);
              if (!match) return <a href={href}>{children}</a>;
              const n = Number(match[1]);
              return (
                <CitationChip
                  n={n}
                  source={m.sources.find((s) => s.n === n)}
                  citation={m.citations.find((c) => c.n === n)}
                  currentLessonId={lessonId}
                  onSeek={onSeek}
                  onOpenLesson={onOpenLesson}
                />
              );
            },
          }}
        >
          {body}
        </Markdown>
      ) : m.status === "streaming" ? (
        <div className="space-y-2" aria-label="AI đang soạn câu trả lời">
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ) : null}

      {m.status === "error" ? (
        <div role="alert" className="mt-2 rounded-md border border-destructive/40 p-3 text-sm">
          <p>{m.error}</p>
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            <RotateCcw /> Thử lại
          </Button>
        </div>
      ) : null}
      {m.status === "stopped" ? <p className="mt-1 text-xs text-muted-foreground">Đã dừng.</p> : null}

      {m.status === "done" && !m.id.startsWith("local-") ? (
        <div className="mt-1 flex gap-1">
          <Tip label="Câu trả lời hữu ích">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Hữu ích"
              aria-pressed={m.feedback === 1}
              className={cn("size-8", m.feedback === 1 && "text-success")}
              onClick={() => onFeedback(m.feedback === 1 ? null : 1)}
            >
              <ThumbsUp />
            </Button>
          </Tip>
          <Tip label="Câu trả lời chưa tốt">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Chưa tốt"
              aria-pressed={m.feedback === -1}
              className={cn("size-8", m.feedback === -1 && "text-destructive")}
              onClick={() => onFeedback(m.feedback === -1 ? null : -1)}
            >
              <ThumbsDown />
            </Button>
          </Tip>
        </div>
      ) : null}
    </div>
  );
}

/** Số giây còn lại tới retryAt (429), về 0 thì gọi onDone. */
function useCountdown(until: number | null, onDone: () => void) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!until) return;
    const id = window.setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= until) onDone();
    }, 1000);
    return () => window.clearInterval(id);
  }, [until, onDone]);
  return until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0;
}
```

- [ ] **Bước 5: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend/src && git commit -m "feat(web): AI Tutor chat over SSE with citations and feedback"
```

---

## Task 13: Trang học bài

**Files:**
- Create: `frontend/src/lib/study/use-video-progress.ts`, `frontend/src/components/lesson/course-outline.tsx`, `reading-progress.tsx`, `break-reminder.tsx`, `shortcut-help.tsx`, `lesson-view.tsx`, `frontend/src/app/learn/[slug]/[lessonId]/page.tsx`

Bố cục theo design-system §7.2:

- **Desktop:** mục lục bên trái (thu gọn được), nội dung ở giữa, Tutor 400px bên phải.
- **Điện thoại:** video dính trên cùng, nút nổi "Hỏi AI" mở khung trượt cao 85%.
- Thanh tiến độ đọc 2px màu accent ở mép trên.
- Mở lại bài thì về đúng chỗ đọc dở (localStorage) và đúng giây video (server).
- Giảng viên xem bài thì có huy hiệu "Chế độ xem trước" và tiến độ **không** được lưu.

Phần này được kiểm thử bằng E2E ở Task 16 (luồng học bài đầy đủ ở 375 và 1280px).

- [ ] **Bước 1: Lưu tiến độ video** (`src/lib/study/use-video-progress.ts`)

Lưu mỗi 15 giây xem, khi tạm dừng và khi ẩn tab. Dùng ref callback có trả về hàm cleanup (React 19).

```ts
"use client";

import * as React from "react";
import type { LessonDetail } from "@/lib/queries";
import { useSaveProgress } from "@/lib/queries";

const SAVE_EVERY_SEC = 15;

/**
 * Lưu vị trí video lên server (PUT /lessons/{id}/progress) mỗi 15 giây xem,
 * khi tạm dừng và khi rời trang; mở lại thì tua tới chỗ cũ.
 * Chỉ học viên mới lưu được (backend trả 403 cho giảng viên) → `track=false`.
 */
export function useVideoProgress(lesson: LessonDetail, track: boolean) {
  const save = useSaveProgress(lesson.id);
  const lastSaved = React.useRef(lesson.progress?.video_position_sec ?? 0);
  const done = lesson.progress?.status === "done";

  const persist = React.useCallback(
    (sec: number) => {
      if (!track) return;
      const pos = Math.floor(sec);
      if (Math.abs(pos - lastSaved.current) < 2) return;
      lastSaved.current = pos;
      save.mutate({ status: done ? "done" : "in_progress", video_position_sec: pos });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [track, done, lesson.id],
  );

  const bind = React.useCallback(
    (video: HTMLVideoElement | null) => {
      if (!video) return;
      const resumeAt = lesson.progress?.video_position_sec ?? 0;
      const onMeta = () => {
        if (resumeAt > 5 && resumeAt < video.duration - 5) video.currentTime = resumeAt;
      };
      const onTime = () => {
        if (Math.abs(video.currentTime - lastSaved.current) >= SAVE_EVERY_SEC) persist(video.currentTime);
      };
      const onPause = () => persist(video.currentTime);
      video.addEventListener("loadedmetadata", onMeta);
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("pause", onPause);
      const onHide = () => document.visibilityState === "hidden" && persist(video.currentTime);
      document.addEventListener("visibilitychange", onHide);
      return () => {
        video.removeEventListener("loadedmetadata", onMeta);
        video.removeEventListener("timeupdate", onTime);
        video.removeEventListener("pause", onPause);
        document.removeEventListener("visibilitychange", onHide);
      };
    },
    [lesson.progress?.video_position_sec, persist],
  );

  return { bind, currentSaved: () => lastSaved.current };
}
```

- [ ] **Bước 2: Các phần của trang**

`src/components/lesson/course-outline.tsx`. Prop `hrefFor` để trình soạn dùng lại component này với link khác:

```tsx
import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import type { CourseDetail } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Mục lục khóa trong trang học bài; bài đang mở được đánh dấu aria-current. */
export function CourseOutline({
  course,
  currentLessonId,
  doneIds,
  onNavigate,
  hrefFor = (id) => `/learn/${course.slug}/${id}`,
}: {
  course: CourseDetail;
  currentLessonId: string;
  doneIds?: Set<string>;
  onNavigate?: () => void;
  /** Link của mỗi bài; mặc định là trang học, trình soạn truyền link soạn bài. */
  hrefFor?: (lessonId: string) => string;
}) {
  return (
    <nav aria-label="Mục lục khóa học" className="space-y-4 p-3">
      {[...course.sections]
        .sort((a, b) => a.position - b.position)
        .map((s, i) => (
          <div key={s.id}>
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Chương {i + 1}. {s.title}
            </p>
            <ul className="mt-1">
              {[...s.lessons]
                .sort((a, b) => a.position - b.position)
                .map((l) => {
                  const current = l.id === currentLessonId;
                  const done = doneIds?.has(l.id);
                  return (
                    <li key={l.id}>
                      <Link
                        href={hrefFor(l.id)}
                        onClick={onNavigate}
                        aria-current={current ? "page" : undefined}
                        className={cn(
                          "flex min-h-10 items-start gap-2 rounded-md px-2 py-2 text-sm hover:bg-muted",
                          current && "bg-muted font-medium text-primary",
                        )}
                      >
                        {done ? (
                          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="Đã học" />
                        ) : (
                          <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                        )}
                        {l.title}
                      </Link>
                    </li>
                  );
                })}
            </ul>
          </div>
        ))}
    </nav>
  );
}
```

`src/components/lesson/reading-progress.tsx`:

```tsx
"use client";

import * as React from "react";
import { scrollPosition } from "@/lib/study/storage";

/**
 * Thanh 2px màu accent ở mép trên cho biết đã đọc tới đâu, đồng thời
 * nhớ vị trí cuộn của bài và khôi phục khi mở lại (design-system §7.2, §8).
 */
export function ReadingProgress({ lessonId, ready }: { lessonId: string; ready: boolean }) {
  const [pct, setPct] = React.useState(0);

  React.useEffect(() => {
    if (!ready) return;
    const ratio = scrollPosition.get(lessonId);
    const max = document.documentElement.scrollHeight - window.innerHeight;
    if (ratio > 0.02 && max > 0) window.scrollTo({ top: ratio * max });
  }, [lessonId, ready]);

  React.useEffect(() => {
    let timer: number | undefined;
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = max > 0 ? window.scrollY / max : 0;
      setPct(Math.round(ratio * 100));
      window.clearTimeout(timer);
      timer = window.setTimeout(() => scrollPosition.set(lessonId, ratio), 400);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.clearTimeout(timer);
    };
  }, [lessonId]);

  return (
    <div className="fixed inset-x-0 top-0 z-40 h-0.5" aria-hidden>
      <div className="h-full bg-accent transition-[width] duration-150" style={{ width: `${pct}%` }} />
    </div>
  );
}
```

`src/components/lesson/break-reminder.tsx`:

```tsx
"use client";

import { Eye } from "lucide-react";
import { Dialog as D } from "radix-ui";
import { Button } from "@/components/ui/button";
import { useBreakReminder } from "@/lib/study/use-break-reminder";

/** Hộp nhắc nghỉ mắt 20 giây sau 45 phút học (design-system §8). */
export function BreakReminder({ paused = false }: { paused?: boolean }) {
  const r = useBreakReminder({ paused });
  return (
    <D.Root open={r.due} onOpenChange={(o) => !o && r.done()}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <D.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-surface p-6 text-center shadow-lg">
          <Eye className="mx-auto size-8 text-primary" aria-hidden />
          <D.Title className="mt-3 text-lg font-semibold">Nghỉ mắt một chút nhé</D.Title>
          <D.Description className="mt-2 text-muted-foreground">
            Bạn đã học 45 phút. Hãy nhìn ra xa khoảng 6 mét trong 20 giây để mắt được nghỉ.
          </D.Description>
          <div className="mt-6 flex flex-col gap-2">
            <Button onClick={r.done}>Đã nghỉ</Button>
            <Button variant="outline" onClick={r.snooze}>
              Nhắc sau 15 phút
            </Button>
            <Button variant="link" className="mx-auto" onClick={r.disable}>
              Tắt nhắc
            </Button>
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
```

`src/components/lesson/shortcut-help.tsx`:

```tsx
"use client";

import { Dialog, DialogContent } from "@/components/ui/dialog";

const SHORTCUTS = [
  ["/", "Mở AI Tutor"],
  ["F", "Bật/tắt chế độ tập trung"],
  ["←  →", "Bài trước / bài sau"],
  ["Esc", "Đóng panel"],
  ["?", "Xem bảng phím tắt này"],
];

export function ShortcutHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Phím tắt">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="contents">
              <dt>
                <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
              </dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Bước 3: Trang học bài** (`src/components/lesson/lesson-view.tsx`)

```tsx
"use client";

import {
  AArrowDown,
  AArrowUp,
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Keyboard,
  ListTree,
  Maximize2,
  MessageCircleQuestion,
  Minimize2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ThemeSwitcher } from "@/components/app/theme-switcher";
import { ErrorState } from "@/components/app/states";
import { Markdown } from "@/components/content/markdown";
import { TutorPanel } from "@/components/tutor/tutor-panel";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Badge, Skeleton, Tip } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { flattenLessons, useCourse, useLesson, useLessonVideo, useSaveProgress } from "@/lib/queries";
import { lastLesson, READER_MAX, READER_MIN, readerSize } from "@/lib/study/storage";
import { useShortcuts } from "@/lib/study/use-shortcuts";
import { useVideoProgress } from "@/lib/study/use-video-progress";
import { useTutorChat } from "@/lib/tutor/use-tutor-chat";
import { cn } from "@/lib/utils";
import { BreakReminder } from "./break-reminder";
import { CourseOutline } from "./course-outline";
import { ReadingProgress } from "./reading-progress";
import { ShortcutHelp } from "./shortcut-help";

function useIsDesktop() {
  const [desktop, setDesktop] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return desktop;
}

export function LessonView({ slug, lessonId }: { slug: string; lessonId: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const course = useCourse(slug);
  const lesson = useLesson(lessonId);
  const video = useLessonVideo(lessonId);
  const desktop = useIsDesktop();

  // LessonView chỉ render trên trình duyệt (sau RequireAuth) nên đọc localStorage lúc khởi tạo được
  const [fontPx, setFontPx] = React.useState(() => readerSize.get());
  const [focus, setFocus] = React.useState(false);
  const [outlineOpen, setOutlineOpen] = React.useState(true); // desktop
  const [outlineSheet, setOutlineSheet] = React.useState(false); // điện thoại
  const [tutorOpen, setTutorOpen] = React.useState(false);
  const [helpOpen, setHelpOpen] = React.useState(false);
  const videoRef = React.useRef<HTMLVideoElement | null>(null);

  const changeFont = (d: number) => {
    const next = Math.min(READER_MAX, Math.max(READER_MIN, fontPx + d));
    setFontPx(next);
    readerSize.set(next);
  };

  const lessons = course.data ? flattenLessons(course.data) : [];
  const index = lessons.findIndex((l) => l.id === lessonId);
  const prev = index > 0 ? lessons[index - 1] : null;
  const next = index >= 0 && index < lessons.length - 1 ? lessons[index + 1] : null;
  const go = (id: string) => router.push(`/learn/${slug}/${id}`);

  React.useEffect(() => {
    if (course.data) lastLesson.set(course.data.id, lessonId);
  }, [course.data, lessonId]);

  const chat = useTutorChat({ courseId: course.data?.id ?? "", lessonId }, !!course.data && tutorOpen);

  useShortcuts({
    "/": () => setTutorOpen(true),
    f: () => setFocus((v) => !v),
    ArrowLeft: () => prev && go(prev.id),
    ArrowRight: () => next && go(next.id),
    Escape: () => (tutorOpen ? setTutorOpen(false) : setFocus(false)),
    "?": () => setHelpOpen(true),
  });

  if (course.isError || lesson.isError)
    return (
      <div className="p-6">
        <ErrorState
          error={course.error ?? lesson.error}
          onRetry={() => {
            course.refetch();
            lesson.refetch();
          }}
        />
      </div>
    );

  const isStudent = user?.role === "student";
  const seek = (sec: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = sec;
    v.scrollIntoView({ behavior: "smooth", block: "center" });
    void v.play().catch(() => undefined);
  };
  const openLesson = (id: string) => {
    setTutorOpen(false);
    go(id);
  };
  const tutor = course.data ? (
    <TutorPanel chat={chat} lessonId={lessonId} onSeek={seek} onOpenLesson={openLesson} />
  ) : null;

  return (
    <div className="min-h-dvh" style={{ ["--reader-size" as string]: `${fontPx}px` }}>
      <ReadingProgress lessonId={lessonId} ready={!!lesson.data} />

      {/* Thanh trên cùng */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-1 border-b bg-background/95 px-2 backdrop-blur md:px-4">
        <Button asChild variant="ghost" size="icon" aria-label="Về trang khóa học">
          <Link href={`/courses/${slug}`}>
            <ArrowLeft />
          </Link>
        </Button>
        <Tip label="Mục lục">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Mục lục"
            aria-expanded={desktop ? outlineOpen && !focus : outlineSheet}
            onClick={() => (desktop ? setOutlineOpen((v) => !v) : setOutlineSheet(true))}
          >
            <ListTree />
          </Button>
        </Tip>
        <p className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{course.data?.title}</p>
        <div className="hidden items-center gap-1 md:flex">
          <Tip label="Chữ nhỏ hơn">
            <Button variant="ghost" size="icon" aria-label="Chữ nhỏ hơn" disabled={fontPx <= READER_MIN} onClick={() => changeFont(-1)}>
              <AArrowDown />
            </Button>
          </Tip>
          <Tip label="Chữ lớn hơn">
            <Button variant="ghost" size="icon" aria-label="Chữ lớn hơn" disabled={fontPx >= READER_MAX} onClick={() => changeFont(1)}>
              <AArrowUp />
            </Button>
          </Tip>
          <ThemeSwitcher compact />
          <Tip label={focus ? "Thoát chế độ tập trung (F)" : "Chế độ tập trung (F)"}>
            <Button variant="ghost" size="icon" aria-label="Chế độ tập trung" aria-pressed={focus} onClick={() => setFocus((v) => !v)}>
              {focus ? <Minimize2 /> : <Maximize2 />}
            </Button>
          </Tip>
          <Tip label="Phím tắt (?)">
            <Button variant="ghost" size="icon" aria-label="Phím tắt" onClick={() => setHelpOpen(true)}>
              <Keyboard />
            </Button>
          </Tip>
        </div>
        <Button variant="ghost" className="hidden lg:inline-flex" aria-pressed={tutorOpen} onClick={() => setTutorOpen((v) => !v)}>
          <MessageCircleQuestion /> Hỏi AI
        </Button>
      </header>

      <div className="flex">
        {/* Mục lục bên trái (desktop) */}
        {desktop && outlineOpen && !focus && course.data ? (
          <aside className="sticky top-14 h-[calc(100dvh-3.5rem)] w-72 shrink-0 overflow-y-auto border-r">
            <CourseOutline course={course.data} currentLessonId={lessonId} />
          </aside>
        ) : null}

        {/* Nội dung bài */}
        <main id="main" className="min-w-0 flex-1 px-4 pb-28 pt-6 md:px-8 lg:pb-12">
          <article className="mx-auto max-w-[68ch]" style={{ maxWidth: `calc(68ch * ${fontPx} / 16)` }}>
            {lesson.isPending ? (
              <div className="space-y-4" aria-busy="true" aria-label="Đang tải bài học">
                <Skeleton className="h-8 w-2/3" />
                <Skeleton className="aspect-video w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
              </div>
            ) : (
              <>
                {!isStudent ? <Badge tone="accent" className="mb-3">Chế độ xem trước — tiến độ không được lưu</Badge> : null}
                <p className="text-sm text-muted-foreground">
                  Bài {index + 1}/{lessons.length}
                  {lessons[index]?.sectionTitle ? ` · ${lessons[index].sectionTitle}` : ""}
                </p>
                <h1 className="mt-1 text-2xl font-semibold md:text-3xl">{lesson.data.title}</h1>

                {video.data ? (
                  <LessonVideo
                    key={lessonId}
                    src={video.data}
                    lesson={lesson.data}
                    track={isStudent}
                    videoRef={videoRef}
                  />
                ) : null}

                {lesson.data.content_md ? (
                  <Markdown className="mt-6">{lesson.data.content_md}</Markdown>
                ) : (
                  <p className="mt-6 text-muted-foreground">Bài này chưa có nội dung đọc.</p>
                )}

                <LessonFooter
                  lesson={lesson.data}
                  isStudent={isStudent}
                  prev={prev}
                  next={next}
                  onGo={go}
                  videoRef={videoRef}
                />
              </>
            )}
          </article>
        </main>

        {/* Tutor bên phải (desktop) */}
        {desktop && tutorOpen ? (
          <aside aria-label="AI Tutor" className="sticky top-14 flex h-[calc(100dvh-3.5rem)] w-[400px] shrink-0 flex-col border-l bg-surface">
            <div className="flex h-12 items-center justify-between border-b px-4">
              <h2 className="font-semibold">AI Tutor</h2>
              <Button variant="ghost" size="icon" aria-label="Đóng AI Tutor" onClick={() => setTutorOpen(false)}>
                <X />
              </Button>
            </div>
            <div className="min-h-0 flex-1">{tutor}</div>
          </aside>
        ) : null}
      </div>

      {/* Điện thoại: nút nổi + khung trượt */}
      {!desktop ? (
        <>
          <Button size="lg" className="fixed bottom-4 right-4 z-30 rounded-full shadow-lg" onClick={() => setTutorOpen(true)}>
            <MessageCircleQuestion /> Hỏi AI
          </Button>
          <Sheet open={tutorOpen} onOpenChange={setTutorOpen} title="AI Tutor">
            {tutor}
          </Sheet>
          <Sheet open={outlineSheet} onOpenChange={setOutlineSheet} title="Mục lục" side="left">
            <div className="h-full overflow-y-auto">
              {course.data ? (
                <CourseOutline course={course.data} currentLessonId={lessonId} onNavigate={() => setOutlineSheet(false)} />
              ) : null}
            </div>
          </Sheet>
        </>
      ) : null}

      <ShortcutHelp open={helpOpen} onOpenChange={setHelpOpen} />
      <BreakReminder />
    </div>
  );
}

function LessonVideo({
  src,
  lesson,
  track,
  videoRef,
}: {
  src: string;
  lesson: NonNullable<ReturnType<typeof useLesson>["data"]>;
  track: boolean;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const { bind } = useVideoProgress(lesson, track);
  const setRef = React.useCallback(
    (el: HTMLVideoElement | null) => {
      videoRef.current = el;
      return bind(el);
    },
    [bind, videoRef],
  );
  return (
    // Điện thoại: video dính trên cùng khi cuộn (design-system §7.2)
    <div className="sticky top-14 z-20 -mx-4 mt-4 bg-background md:static md:mx-0">
      <video ref={setRef} src={src} controls playsInline preload="metadata" className="aspect-video w-full bg-black md:rounded-lg">
        Trình duyệt không phát được video này.
      </video>
    </div>
  );
}

function LessonFooter({
  lesson,
  isStudent,
  prev,
  next,
  onGo,
  videoRef,
}: {
  lesson: NonNullable<ReturnType<typeof useLesson>["data"]>;
  isStudent: boolean;
  prev: { id: string; title: string } | null;
  next: { id: string; title: string } | null;
  onGo: (id: string) => void;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const save = useSaveProgress(lesson.id);
  const done = lesson.progress?.status === "done";

  async function markDone() {
    try {
      await save.mutateAsync({ status: "done", video_position_sec: Math.floor(videoRef.current?.currentTime ?? lesson.progress?.video_position_sec ?? 0) });
      toast.success("Đã đánh dấu học xong");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="mt-10 border-t pt-6">
      {isStudent ? (
        done ? (
          <p className="flex items-center gap-2 font-medium text-success">
            <CheckCircle2 className="size-5" aria-hidden /> Đã học xong bài này
          </p>
        ) : (
          <Button variant="outline" onClick={markDone} loading={save.isPending} loadingText="Đang lưu…">
            <CheckCircle2 /> Đánh dấu đã học xong
          </Button>
        )
      ) : null}
      <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        {prev ? (
          <Button variant="outline" onClick={() => onGo(prev.id)} className="justify-start">
            <ChevronLeft /> <span className="truncate">Bài trước: {prev.title}</span>
          </Button>
        ) : (
          <span />
        )}
        {next ? (
          // Bài tiếp là nút chính khi đã học xong (gợi ý bước tiếp theo); trước đó là nút phụ
          <Button variant={done || !isStudent ? "default" : "outline"} onClick={() => onGo(next.id)} className={cn("justify-end")}>
            <span className="truncate">Bài tiếp: {next.title}</span> <ChevronRight />
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">Đây là bài cuối của khóa.</p>
        )}
      </div>
    </div>
  );
}
```

`src/app/learn/[slug]/[lessonId]/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { RequireAuth } from "@/lib/auth/require-auth";
import { LessonView } from "@/components/lesson/lesson-view";

export default function LearnPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth>
      <LessonView slug={slug} lessonId={lessonId} />
    </RequireAuth>
  );
}
```

- [ ] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test && npm run build
git add frontend/src && git commit -m "feat(web): lesson page with reader, video resume, tutor panel and focus mode"
```

Expected: build liệt kê `ƒ /learn/[slug]/[lessonId]`.

---

## Task 14: Giảng viên: danh sách khóa và trình soạn khóa

**Files:**
- Create: `frontend/src/lib/teach-queries.ts`, `frontend/src/components/teach/inline-add.tsx`, `curriculum.tsx`, `course-editor.tsx`, `frontend/src/app/(main)/teach/page.tsx`, `frontend/src/app/(main)/teach/[slug]/page.tsx`
- Test: `frontend/src/lib/teach-queries.test.ts`

Quy tắc theo design-system §5.3 (Giảng viên):

- **Xuất bản** là nút chính duy nhất trên thanh trên cùng, bấm thì hỏi xác nhận.
- Sắp xếp bằng kéo thả (chuột; bàn phím: Space rồi ↑↓) **và** nút ↑↓ (cho điện thoại). Thứ tự đổi ngay trên màn hình, lưu lỗi thì quay về thứ tự cũ.
- Xóa nằm trong menu `⋯`. Hộp xác nhận ghi rõ số bài sẽ mất. Xóa cả khóa thì phải gõ lại tên khóa.
- Thông tin khóa tự lưu, có dòng "Đã lưu lúc …".

- [ ] **Bước 1: Viết test (sẽ fail)**

`src/lib/teach-queries.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { moveItem } from "./teach-queries";

describe("moveItem", () => {
  it("chuyển phần tử lên/xuống", () => {
    expect(moveItem(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(moveItem(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
  });
  it("giữ nguyên khi vượt biên", () => {
    const list = ["a", "b"];
    expect(moveItem(list, 0, -1)).toBe(list);
    expect(moveItem(list, 1, 2)).toBe(list);
  });
});
```

Run: `npx vitest run src/lib/teach-queries.test.ts`
Expected: FAIL, lỗi `Failed to resolve import "./teach-queries"`.

- [ ] **Bước 2: Cài đặt `src/lib/teach-queries.ts`**

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qk, type CourseDetail } from "@/lib/queries";

export type SourceOut = components["schemas"]["SourceOut"];

export function useTeacherCourses(page = 1) {
  return useQuery({
    queryKey: qk.teacherCourses(page),
    queryFn: () => unwrap(api.GET("/api/v1/teacher/courses", { params: { query: { page, size: 50 } } })),
  });
}

function useRefreshingMutation<A>(slug: string, fn: (a: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: qk.course(slug) }) });
}

/** Mọi thao tác sửa cấu trúc khóa: gọi API rồi tải lại chi tiết khóa (nguồn sự thật duy nhất). */
export function useCourseMutations(course: CourseDetail) {
  const qc = useQueryClient();
  const slug = course.slug;
  const refresh = () => qc.invalidateQueries({ queryKey: qk.course(slug) });
  const cid = { params: { path: { course_id: course.id } } };

  return {
    updateCourse: useRefreshingMutation(slug, (body: components["schemas"]["CourseUpdate"]) => unwrap(api.PATCH("/api/v1/courses/{course_id}", { ...cid, body }))),
    publish: useRefreshingMutation(slug, () => unwrap(api.POST("/api/v1/courses/{course_id}/publish", cid))),
    deleteCourse: useMutation({ mutationFn: () => unwrap(api.DELETE("/api/v1/courses/{course_id}", cid)) }),
    addSection: useRefreshingMutation(slug, (title: string) => unwrap(api.POST("/api/v1/courses/{course_id}/sections", { ...cid, body: { title } }))),
    renameSection: useRefreshingMutation(slug, ({ id, title }: { id: string; title: string }) =>
      unwrap(api.PATCH("/api/v1/sections/{section_id}", { params: { path: { section_id: id } }, body: { title } })),
    ),
    deleteSection: useRefreshingMutation(slug, (id: string) => unwrap(api.DELETE("/api/v1/sections/{section_id}", { params: { path: { section_id: id } } }))),
    addLesson: useRefreshingMutation(slug, ({ sectionId, title }: { sectionId: string; title: string }) =>
      unwrap(api.POST("/api/v1/sections/{section_id}/lessons", { params: { path: { section_id: sectionId } }, body: { title, content_md: "" } })),
    ),
    deleteLesson: useRefreshingMutation(slug, (id: string) => unwrap(api.DELETE("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: id } } }))),
    /** Sắp xếp lạc quan: đổi thứ tự ngay trên màn hình, lỗi thì trả về thứ tự cũ (design-system §5.3). */
    reorder: useMutation({
      mutationFn: (sections: CourseDetail["sections"]) =>
        unwrap(
          api.PATCH("/api/v1/courses/{course_id}/reorder", {
            ...cid,
            body: { sections: sections.map((s) => ({ id: s.id, lesson_ids: s.lessons.map((l) => l.id) })) },
          }),
        ),
      onMutate: async (sections) => {
        await qc.cancelQueries({ queryKey: qk.course(course.slug) });
        const previous = qc.getQueryData<CourseDetail>(qk.course(course.slug));
        qc.setQueryData<CourseDetail>(qk.course(course.slug), (old) =>
          old
            ? {
                ...old,
                sections: sections.map((s, i) => ({ ...s, position: i, lessons: s.lessons.map((l, j) => ({ ...l, position: j })) })),
              }
            : old,
        );
        return { previous };
      },
      onError: (_e, _v, ctx) => ctx?.previous && qc.setQueryData(qk.course(course.slug), ctx.previous),
      onSettled: refresh,
    }),
  };
}

/** Sắp xếp sections/lessons theo position, trả về bản sao để chỉnh. */
export function sortedSections(course: CourseDetail) {
  return [...course.sections]
    .sort((a, b) => a.position - b.position)
    .map((s) => ({ ...s, lessons: [...s.lessons].sort((a, b) => a.position - b.position) }));
}

export function moveItem<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length || from === to) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function useLessonSources(lessonId: string) {
  return useQuery({
    queryKey: qk.sources(lessonId),
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/sources", { params: { path: { lesson_id: lessonId } } })),
    // còn tài liệu đang xử lý thì hỏi lại mỗi 3 giây; xong hết thì dừng
    refetchInterval: (q) => (q.state.data?.some((s) => s.status === "pending" || s.status === "processing") ? 3000 : false),
  });
}

export function useSourceActions(lessonId: string) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: qk.sources(lessonId) });
  return {
    attach: useMutation({
      mutationFn: (assetId: string) =>
        unwrap(api.POST("/api/v1/lessons/{lesson_id}/sources", { params: { path: { lesson_id: lessonId } }, body: { asset_id: assetId } })),
      onSuccess: refresh,
    }),
    reprocess: useMutation({
      mutationFn: (sourceId: string) =>
        unwrap(api.POST("/api/v1/sources/{source_id}/reprocess", { params: { path: { source_id: sourceId } } })),
      onSuccess: refresh,
    }),
  };
}

export function useSourcePages(sourceId: string | null, page: number) {
  return useQuery({
    queryKey: ["source-pages", sourceId, page],
    enabled: !!sourceId,
    queryFn: () =>
      unwrap(api.GET("/api/v1/sources/{source_id}/pages", { params: { path: { source_id: sourceId! }, query: { page, size: 10 } } })),
  });
}
```

Run: `npx vitest run src/lib/teach-queries.test.ts`
Expected: PASS (2 test).

- [ ] **Bước 3: Giao diện**

`src/components/teach/inline-add.tsx`:

```tsx
"use client";

import { Plus } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Nút "Thêm …" mở ô nhập tên ngay tại chỗ, con trỏ tự vào ô (design-system §5.3). */
export function InlineAdd({ label, placeholder, onAdd }: { label: string; placeholder: string; onAdd: (title: string) => Promise<unknown> }) {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState("");
  const [pending, setPending] = React.useState(false);

  if (!editing)
    return (
      <Button variant="outline" size="sm" className="h-10 md:h-8" onClick={() => setEditing(true)}>
        <Plus /> {label}
      </Button>
    );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setPending(true);
    try {
      await onAdd(value.trim());
      setValue("");
      setEditing(false);
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex gap-2">
      <Input
        autoFocus
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        maxLength={200}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
      />
      <Button type="submit" variant="outline" loading={pending} loadingText="Đang thêm…">
        Thêm
      </Button>
      <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
        Hủy
      </Button>
    </form>
  );
}
```

`src/components/teach/curriculum.tsx`:

```tsx
"use client";

import { closestCenter, DndContext, type DragEndEvent, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowDown, ArrowUp, FileText, GripVertical, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { errorMessage } from "@/lib/api/errors";
import type { CourseDetail } from "@/lib/queries";
import { moveItem, sortedSections, useCourseMutations } from "@/lib/teach-queries";
import { InlineAdd } from "./inline-add";

type Sections = ReturnType<typeof sortedSections>;
type Mut = ReturnType<typeof useCourseMutations>;

/**
 * Mục lục chương/bài của trình soạn. Sắp xếp bằng kéo thả (chuột, bàn phím: Space rồi ↑↓)
 * hoặc nút ↑↓ (điện thoại). Mọi thay đổi thứ tự lưu ngay, lỗi thì trả về thứ tự cũ.
 */
export function Curriculum({ course, mut }: { course: CourseDetail; mut: Mut }) {
  const sections = sortedSections(course);
  const [pendingDelete, setPendingDelete] = React.useState<
    { kind: "section"; id: string; title: string; lessons: number } | { kind: "lesson"; id: string; title: string } | null
  >(null);

  const reorder = (next: Sections) =>
    mut.reorder.mutate(next, { onError: (err) => toast.error(`Không lưu được thứ tự: ${errorMessage(err)}`) });

  const moveSection = (from: number, to: number) => reorder(moveItem(sections, from, to));
  const moveLesson = (si: number, from: number, to: number) =>
    reorder(sections.map((s, i) => (i === si ? { ...s, lessons: moveItem(s.lessons, from, to) } : s)));

  const run = async (p: Promise<unknown>, ok: string) => {
    try {
      await p;
      toast.success(ok);
    } catch (err) {
      toast.error(errorMessage(err));
      throw err;
    }
  };

  return (
    <section aria-labelledby="curriculum-title">
      <div className="mb-3 flex items-center justify-between">
        <h2 id="curriculum-title" className="text-lg font-semibold">
          Nội dung khóa học
        </h2>
      </div>
      {sections.length === 0 ? (
        <p className="mb-3 text-sm text-muted-foreground">Bắt đầu bằng việc thêm chương đầu tiên.</p>
      ) : null}
      <ol className="space-y-4">
        {sections.map((s, si) => (
          <SectionCard
            key={s.id}
            course={course}
            section={s}
            index={si}
            count={sections.length}
            mut={mut}
            onMove={(to) => moveSection(si, to)}
            onMoveLesson={(from, to) => moveLesson(si, from, to)}
            onDelete={() => setPendingDelete({ kind: "section", id: s.id, title: s.title, lessons: s.lessons.length })}
            onDeleteLesson={(l) => setPendingDelete({ kind: "lesson", id: l.id, title: l.title })}
          />
        ))}
      </ol>
      <div className="mt-4">
        <InlineAdd label="Thêm chương" placeholder="Tên chương mới" onAdd={(t) => run(mut.addSection.mutateAsync(t), "Đã thêm chương")} />
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        destructive
        title={pendingDelete?.kind === "section" ? `Xóa chương “${pendingDelete.title}”?` : `Xóa bài “${pendingDelete?.title}”?`}
        description={
          pendingDelete?.kind === "section"
            ? `Chương này có ${pendingDelete.lessons} bài. Toàn bộ bài, tài liệu và tiến độ học của các bài đó sẽ bị xóa và không khôi phục được.`
            : "Nội dung, video, tài liệu PDF và tiến độ học của bài sẽ bị xóa và không khôi phục được."
        }
        confirmLabel={pendingDelete?.kind === "section" ? "Xóa chương" : "Xóa bài"}
        pendingLabel="Đang xóa…"
        onConfirm={() =>
          pendingDelete!.kind === "section"
            ? run(mut.deleteSection.mutateAsync(pendingDelete!.id), "Đã xóa chương")
            : run(mut.deleteLesson.mutateAsync(pendingDelete!.id), "Đã xóa bài")
        }
      />
    </section>
  );
}

function SectionCard({
  course,
  section,
  index,
  count,
  mut,
  onMove,
  onMoveLesson,
  onDelete,
  onDeleteLesson,
}: {
  course: CourseDetail;
  section: Sections[number];
  index: number;
  count: number;
  mut: Mut;
  onMove: (to: number) => void;
  onMoveLesson: (from: number, to: number) => void;
  onDelete: () => void;
  onDeleteLesson: (l: { id: string; title: string }) => void;
}) {
  const [renaming, setRenaming] = React.useState(false);
  const [title, setTitle] = React.useState(section.title);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function onDragEnd(e: DragEndEvent) {
    if (!e.over || e.active.id === e.over.id) return;
    const from = section.lessons.findIndex((l) => l.id === e.active.id);
    const to = section.lessons.findIndex((l) => l.id === e.over!.id);
    onMoveLesson(from, to);
  }

  async function saveTitle(e: React.FormEvent) {
    e.preventDefault();
    try {
      await mut.renameSection.mutateAsync({ id: section.id, title: title.trim() });
      setRenaming(false);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <li className="rounded-lg border bg-surface">
      <div className="flex items-center gap-1 border-b px-3 py-2">
        {renaming ? (
          <form onSubmit={saveTitle} className="flex flex-1 gap-2">
            <Input aria-label="Tên chương" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
            <Button type="submit" variant="outline" loading={mut.renameSection.isPending} loadingText="Đang lưu…">
              Lưu
            </Button>
          </form>
        ) : (
          <h3 className="flex-1 font-medium">
            Chương {index + 1}. {section.title}
          </h3>
        )}
        <Button variant="ghost" size="icon" aria-label={`Đưa chương ${section.title} lên`} disabled={index === 0} onClick={() => onMove(index - 1)}>
          <ArrowUp />
        </Button>
        <Button variant="ghost" size="icon" aria-label={`Đưa chương ${section.title} xuống`} disabled={index === count - 1} onClick={() => onMove(index + 1)}>
          <ArrowDown />
        </Button>
        <Menu>
          <MenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={`Thao tác với chương ${section.title}`}>
              <MoreHorizontal />
            </Button>
          </MenuTrigger>
          <MenuContent>
            <MenuItem onSelect={() => setRenaming(true)}>
              <Pencil /> Đổi tên
            </MenuItem>
            <MenuSeparator />
            <MenuItem destructive onSelect={onDelete}>
              <Trash2 /> Xóa chương
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={section.lessons.map((l) => l.id)} strategy={verticalListSortingStrategy}>
          <ul>
            {section.lessons.map((l, li) => (
              <LessonRow
                key={l.id}
                href={`/teach/${course.slug}/lessons/${l.id}`}
                lesson={l}
                first={li === 0}
                last={li === section.lessons.length - 1}
                onUp={() => onMoveLesson(li, li - 1)}
                onDown={() => onMoveLesson(li, li + 1)}
                onDelete={() => onDeleteLesson(l)}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>

      <div className="px-3 py-3">
        <InlineAdd
          label="Thêm bài"
          placeholder="Tên bài mới"
          onAdd={async (t) => {
            try {
              await mut.addLesson.mutateAsync({ sectionId: section.id, title: t });
              toast.success("Đã thêm bài");
            } catch (err) {
              toast.error(errorMessage(err));
              throw err;
            }
          }}
        />
      </div>
    </li>
  );
}

function LessonRow({
  href,
  lesson,
  first,
  last,
  onUp,
  onDown,
  onDelete,
}: {
  href: string;
  lesson: { id: string; title: string };
  first: boolean;
  last: boolean;
  onUp: () => void;
  onDown: () => void;
  onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: lesson.id });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-1 border-b px-2 py-1 last:border-b-0 ${isDragging ? "relative z-10 bg-muted shadow" : ""}`}
    >
      <button
        ref={setActivatorNodeRef}
        type="button"
        aria-label={`Kéo để sắp xếp bài ${lesson.title}`}
        className="hidden size-10 cursor-grab items-center justify-center rounded text-muted-foreground hover:bg-muted md:inline-flex"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>
      <Link href={href} className="flex min-h-10 flex-1 items-center gap-2 rounded px-2 text-sm hover:text-primary hover:underline">
        <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        {lesson.title}
      </Link>
      <Button variant="ghost" size="icon" aria-label={`Đưa bài ${lesson.title} lên`} disabled={first} onClick={onUp}>
        <ArrowUp />
      </Button>
      <Button variant="ghost" size="icon" aria-label={`Đưa bài ${lesson.title} xuống`} disabled={last} onClick={onDown}>
        <ArrowDown />
      </Button>
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={`Thao tác với bài ${lesson.title}`}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          <MenuItem destructive onSelect={onDelete}>
            <Trash2 /> Xóa bài
          </MenuItem>
        </MenuContent>
      </Menu>
    </li>
  );
}
```

`src/components/teach/course-editor.tsx`:

```tsx
"use client";

import { Eye, Globe, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type CourseDetail, flattenLessons, useCourse } from "@/lib/queries";
import { useCourseMutations } from "@/lib/teach-queries";
import { autosaveLabel, useAutosave } from "@/lib/use-autosave";
import { Curriculum } from "./curriculum";

export function CourseEditor({ slug }: { slug: string }) {
  const course = useCourse(slug);
  if (course.isPending)
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Đang tải">
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  if (course.isError) return <ErrorState error={course.error} onRetry={() => course.refetch()} />;
  return <Editor key={course.data.id} course={course.data} />;
}

function Editor({ course }: { course: CourseDetail }) {
  const router = useRouter();
  const mut = useCourseMutations(course);
  const [publishOpen, setPublishOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const firstLesson = flattenLessons(course)[0];

  return (
    <>
      {/* Thanh trên cùng: duy nhất 1 nút chính (Xuất bản) */}
      <div className="mb-6 flex flex-wrap items-center gap-3 md:mb-8">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted-foreground">
            <Link href="/teach" className="hover:underline">
              Khóa đang dạy
            </Link>{" "}
            ›
          </p>
          <h1 className="truncate text-2xl font-semibold md:text-3xl">{course.title}</h1>
        </div>
        {course.status === "published" ? <Badge tone="success">Đã xuất bản</Badge> : <Badge>Nháp</Badge>}
        {firstLesson ? (
          <Button asChild variant="outline">
            <Link href={`/learn/${course.slug}/${firstLesson.id}`}>
              <Eye /> Xem như học viên
            </Link>
          </Button>
        ) : null}
        {course.status !== "published" ? (
          <Button onClick={() => setPublishOpen(true)}>
            <Globe /> Xuất bản
          </Button>
        ) : null}
      </div>

      <p className="mb-6 rounded-md border border-dashed p-3 text-sm text-muted-foreground md:hidden">
        Soạn nội dung dài nên dùng máy tính. Trên điện thoại bạn vẫn sửa tên, nội dung ngắn và thứ tự được.
      </p>

      <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
        <Curriculum course={course} mut={mut} />
        <div className="space-y-8">
          <CourseInfo course={course} mut={mut} />
          <section className="rounded-lg border border-destructive/30 p-4">
            <h2 className="font-semibold">Vùng nguy hiểm</h2>
            <p className="mt-1 text-sm text-muted-foreground">Xóa khóa học cùng toàn bộ chương, bài và tài liệu.</p>
            <Button variant="destructive-outline" className="mt-3" onClick={() => setDeleteOpen(true)}>
              <Trash2 /> Xóa khóa học
            </Button>
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        title="Xuất bản khóa học?"
        description="Học viên sẽ tìm thấy và đăng ký được khóa học này. Bạn vẫn sửa nội dung được sau khi xuất bản."
        confirmLabel="Xuất bản"
        pendingLabel="Đang xuất bản…"
        onConfirm={async () => {
          try {
            await mut.publish.mutateAsync(undefined);
            toast.success("Khóa học đã được xuất bản");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        destructive
        title={`Xóa khóa học “${course.title}”?`}
        description={`Khóa có ${flattenLessons(course).length} bài. Mọi nội dung, video, tài liệu sẽ bị xóa vĩnh viễn.`}
        confirmText={course.title}
        confirmLabel="Xóa vĩnh viễn"
        pendingLabel="Đang xóa…"
        onConfirm={async () => {
          try {
            await mut.deleteCourse.mutateAsync();
            toast.success("Đã xóa khóa học");
            router.replace("/teach");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </>
  );
}

function CourseInfo({ course, mut }: { course: CourseDetail; mut: ReturnType<typeof useCourseMutations> }) {
  const [value, setValue] = React.useState({ title: course.title, description: course.description });
  const tooShort = value.title.trim().length < 3;
  const autosave = useAutosave(value, (v) => mut.updateCourse.mutateAsync({ title: v.title.trim(), description: v.description }), {
    enabled: !tooShort,
  });

  return (
    <section aria-labelledby="info-title" className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 id="info-title" className="text-lg font-semibold">
          Thông tin khóa học
        </h2>
        <span aria-live="polite" className="text-xs text-muted-foreground">
          {autosaveLabel(autosave.state)}
        </span>
      </div>
      <Field id="c-title" label="Tên khóa học" error={tooShort ? "Ít nhất 3 ký tự" : undefined}>
        <Input value={value.title} maxLength={200} onChange={(e) => setValue((v) => ({ ...v, title: e.target.value }))} />
      </Field>
      <Field id="c-desc" label="Mô tả (markdown)">
        <Textarea
          rows={6}
          maxLength={5000}
          value={value.description}
          onChange={(e) => setValue((v) => ({ ...v, description: e.target.value }))}
        />
      </Field>
    </section>
  );
}
```

`src/app/(main)/teach/page.tsx`:

```tsx
"use client";

import { GraduationCap, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { api, unwrap } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { RequireAuth } from "@/lib/auth/require-auth";
import { useTeacherCourses } from "@/lib/teach-queries";

export default function TeachPage() {
  return (
    <RequireAuth staff>
      <TeacherCourses />
    </RequireAuth>
  );
}

function TeacherCourses() {
  const courses = useTeacherCourses();
  const [open, setOpen] = React.useState(false);
  const create = (
    <Button onClick={() => setOpen(true)}>
      <Plus /> Tạo khóa học
    </Button>
  );

  return (
    <>
      <PageHeader title="Khóa đang dạy" actions={courses.data?.items.length ? create : null} />
      {courses.isPending ? (
        <CardListSkeleton count={3} />
      ) : courses.isError ? (
        <ErrorState error={courses.error} onRetry={() => courses.refetch()} />
      ) : courses.data.items.length === 0 ? (
        <EmptyState icon={GraduationCap} title="Bạn chưa có khóa học nào." action={create} />
      ) : (
        <ul className="divide-y rounded-lg border bg-surface">
          {courses.data.items.map((c) => (
            <li key={c.id}>
              <Link href={`/teach/${c.slug}`} className="flex items-center justify-between gap-3 px-4 py-4 hover:bg-muted">
                <span className="font-medium">{c.title}</span>
                {c.status === "published" ? <Badge tone="success">Đã xuất bản</Badge> : <Badge>Nháp</Badge>}
              </Link>
            </li>
          ))}
        </ul>
      )}
      <CreateCourseDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

function CreateCourseDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [error, setError] = React.useState<string>();
  const [pending, setPending] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (title.trim().length < 3) return setError("Tên khóa học ít nhất 3 ký tự");
    setPending(true);
    try {
      const c = await unwrap(api.POST("/api/v1/courses", { body: { title: title.trim(), description } }));
      router.push(`/teach/${c.slug}`);
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Tạo khóa học" description="Bạn có thể sửa tên và mô tả sau. Khóa học ở dạng nháp cho tới khi xuất bản.">
        <form onSubmit={submit} className="space-y-4">
          <Field id="course-title" label="Tên khóa học" error={error}>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} autoFocus />
          </Field>
          <Field id="course-desc" label="Mô tả ngắn (markdown)">
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} maxLength={5000} />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" loading={pending} loadingText="Đang tạo…">
              Tạo và mở trình soạn
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

`src/app/(main)/teach/[slug]/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { CourseEditor } from "@/components/teach/course-editor";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function CourseEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <RequireAuth staff>
      <CourseEditor slug={slug} />
    </RequireAuth>
  );
}
```

- [ ] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend/src && git commit -m "feat(web): teacher course list and curriculum editor with reorder"
```

---

## Task 15: Giảng viên: soạn bài, video, tài liệu PDF

**Files:**
- Create: `frontend/src/components/teach/file-drop.tsx`, `source-list.tsx`, `lesson-editor.tsx`, `frontend/src/app/(main)/teach/[slug]/lessons/[lessonId]/page.tsx`

Theo design-system §7.3, trình soạn bài trên desktop có 3 vùng: mục lục, nội dung (tab Soạn / Xem trước, tự lưu), và cột video + tài liệu.

Trạng thái tài liệu đi theo chuỗi: Đang tải (%) → Đang xử lý (vòng xoay) → Sẵn sàng ✓ / Lỗi (có nút "Xử lý lại"). Danh sách tự hỏi lại mỗi 3 giây khi còn tài liệu đang xử lý, xong hết thì dừng hỏi.

- [ ] **Bước 1: Vùng kéo thả file** (`src/components/teach/file-drop.tsx`)

```tsx
"use client";

import { Upload } from "lucide-react";
import * as React from "react";
import { Progress } from "@/components/ui/misc";
import { UPLOAD_RULES, type UploadKind, uploadAsset, validateFile } from "@/lib/api/upload";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/**
 * Vùng kéo thả + nút chọn file, có thanh tiến trình %. Gọi onUploaded(assetId, file) khi
 * presign → PUT → complete xong (design-system §5.3: "Tải PDF lên").
 */
export function FileDrop({
  kind,
  label,
  onUploaded,
  disabled,
}: {
  kind: UploadKind;
  label: string;
  onUploaded: (assetId: string, file: File) => Promise<unknown>;
  disabled?: boolean;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);
  const [progress, setProgress] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const id = React.useId();

  async function handle(file: File | undefined) {
    if (!file) return;
    setError(null);
    const invalid = validateFile(kind, file);
    if (invalid) return setError(invalid);
    setProgress(0);
    try {
      const assetId = await uploadAsset(kind, file, setProgress);
      await onUploaded(assetId, file);
    } catch (err) {
      setError(err instanceof Error && !("status" in err) ? err.message : errorMessage(err));
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const busy = progress !== null;
  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy && !disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!busy && !disabled) void handle(e.dataTransfer.files[0]);
        }}
        className={cn(
          "flex flex-col items-center gap-2 rounded-lg border border-dashed p-5 text-center text-sm",
          over && "border-primary bg-primary/5",
        )}
      >
        {busy ? (
          <div className="w-full" aria-live="polite">
            <p className="mb-2">Đang tải lên… {progress}%</p>
            <Progress value={progress ?? 0} label="Tiến trình tải lên" />
          </div>
        ) : (
          <>
            <Upload className="size-6 text-muted-foreground" aria-hidden />
            <p className="text-muted-foreground">Kéo thả file vào đây hoặc</p>
            <label
              htmlFor={id}
              className={cn(
                "inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border px-4 font-medium hover:bg-muted md:h-8",
                disabled && "pointer-events-none opacity-50",
              )}
            >
              {label}
            </label>
            <p className="text-xs text-muted-foreground">{UPLOAD_RULES[kind].label}</p>
          </>
        )}
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept={UPLOAD_RULES[kind].mime}
          className="sr-only"
          disabled={busy || disabled}
          onChange={(e) => void handle(e.target.files?.[0])}
        />
      </div>
      {error ? (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Đọc thời lượng video ngay trên trình duyệt để lưu duration_sec. */
export function readVideoDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(v.duration) ? Math.round(v.duration) : null);
    };
    v.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    v.src = url;
  });
}
```

- [ ] **Bước 2: Danh sách tài liệu** (`src/components/teach/source-list.tsx`)

Có hộp xem các trang đã trích, kèm huy hiệu Text / Vision.

```tsx
"use client";

import { AlertTriangle, CheckCircle2, FileText, Loader2, RefreshCw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge, Skeleton } from "@/components/ui/misc";
import { Markdown } from "@/components/content/markdown";
import { ErrorState } from "@/components/app/states";
import { errorMessage } from "@/lib/api/errors";
import { type SourceOut, useLessonSources, useSourceActions, useSourcePages } from "@/lib/teach-queries";
import { FileDrop } from "./file-drop";

const STATUS = {
  pending: { label: "Đang chờ xử lý", tone: "neutral" },
  processing: { label: "Đang xử lý", tone: "primary" },
  ready: { label: "Sẵn sàng", tone: "success" },
  failed: { label: "Lỗi", tone: "destructive" },
} as const;

/**
 * Tài liệu PDF của bài: tải lên → server trích văn bản + tạo embedding (job nền).
 * Danh sách tự hỏi lại trạng thái mỗi 3 giây khi còn tài liệu đang xử lý.
 */
export function SourceList({ lessonId }: { lessonId: string }) {
  const sources = useLessonSources(lessonId);
  const actions = useSourceActions(lessonId);
  const [viewing, setViewing] = React.useState<SourceOut | null>(null);

  return (
    <section aria-labelledby="sources-title" className="space-y-3">
      <h2 id="sources-title" className="font-semibold">
        Tài liệu cho AI Tutor
      </h2>
      <p className="text-sm text-muted-foreground">AI Tutor chỉ trả lời dựa trên các tài liệu ở trạng thái Sẵn sàng.</p>

      {sources.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : sources.isError ? (
        <ErrorState error={sources.error} onRetry={() => sources.refetch()} />
      ) : sources.data.length ? (
        <ul className="space-y-2">
          {sources.data.map((s, i) => (
            <li key={s.id} className="rounded-md border p-3 text-sm">
              <div className="flex items-center gap-2">
                <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="flex-1">Tài liệu {i + 1}</span>
                <Badge tone={STATUS[s.status].tone}>
                  {s.status === "processing" || s.status === "pending" ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
                  {s.status === "ready" ? <CheckCircle2 className="size-3" aria-hidden /> : null}
                  {s.status === "failed" ? <AlertTriangle className="size-3" aria-hidden /> : null}
                  {STATUS[s.status].label}
                </Badge>
              </div>
              {s.status === "ready" ? (
                <p className="mt-1 text-muted-foreground">
                  {s.page_count} trang · {s.chunk_count} đoạn{s.vision_pages ? ` · ${s.vision_pages} trang đọc bằng AI vision` : ""}
                </p>
              ) : null}
              {s.warning ? <p className="mt-1 text-accent">{s.warning}</p> : null}
              {s.status === "failed" && s.error_msg ? <p className="mt-1 text-destructive">{s.error_msg}</p> : null}
              <div className="mt-2 flex gap-2">
                {s.status === "ready" ? (
                  <Button variant="link" size="sm" onClick={() => setViewing(s)}>
                    Xem các trang đã trích
                  </Button>
                ) : null}
                {s.status === "failed" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    loading={actions.reprocess.isPending && actions.reprocess.variables === s.id}
                    loadingText="Đang gửi…"
                    onClick={() =>
                      actions.reprocess.mutate(s.id, {
                        onSuccess: () => toast("Đã gửi xử lý lại"),
                        onError: (err) => toast.error(errorMessage(err)),
                      })
                    }
                  >
                    <RefreshCw /> Xử lý lại
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Chưa có tài liệu nào.</p>
      )}

      <FileDrop
        kind="pdf"
        label="Chọn file PDF"
        onUploaded={async (assetId) => {
          await actions.attach.mutateAsync(assetId);
          toast.success("Đã tải lên. Hệ thống đang xử lý tài liệu…");
        }}
      />

      <SourcePagesDialog source={viewing} onClose={() => setViewing(null)} />
    </section>
  );
}

function SourcePagesDialog({ source, onClose }: { source: SourceOut | null; onClose: () => void }) {
  const [page, setPage] = React.useState(1);
  const pages = useSourcePages(source?.id ?? null, page);
  const totalPages = pages.data ? Math.ceil(pages.data.total / pages.data.size) : 1;
  return (
    <Dialog
      open={!!source}
      onOpenChange={(o) => {
        if (!o) {
          onClose();
          setPage(1);
        }
      }}
    >
      <DialogContent title="Các trang đã trích" className="max-h-[85dvh] max-w-2xl overflow-y-auto">
        {pages.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : pages.isError ? (
          <ErrorState error={pages.error} onRetry={() => pages.refetch()} />
        ) : (
          <div className="space-y-6">
            {pages.data.items.map((p) => (
              <article key={p.page_no} className="rounded-md border p-3">
                <div className="mb-2 flex items-center gap-2 text-sm">
                  <span className="font-medium">Trang {p.page_no}</span>
                  <Badge tone={p.extraction_method === "vision" ? "accent" : "neutral"}>
                    {p.extraction_method === "vision" ? "Vision" : "Text"}
                  </Badge>
                </div>
                <Markdown className="text-sm [--reader-size:14px]">{p.markdown}</Markdown>
              </article>
            ))}
            <div className="flex items-center justify-between">
              <Button variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Trang trước
              </Button>
              <span className="text-sm text-muted-foreground">
                {page}/{totalPages}
              </span>
              <Button variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                Trang sau
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Bước 3: Trình soạn bài**

`src/components/teach/lesson-editor.tsx`. Có cảnh báo `beforeunload` khi còn thay đổi chưa lưu:

```tsx
"use client";

import { ArrowLeft, Eye, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Tabs } from "radix-ui";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { Markdown } from "@/components/content/markdown";
import { CourseOutline } from "@/components/lesson/course-outline";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { api, unwrap } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { type LessonDetail, qk, useCourse, useLesson, useLessonVideo } from "@/lib/queries";
import { autosaveLabel, useAutosave } from "@/lib/use-autosave";
import { useQueryClient } from "@tanstack/react-query";
import { FileDrop, readVideoDuration } from "./file-drop";
import { SourceList } from "./source-list";

export function LessonEditor({ slug, lessonId }: { slug: string; lessonId: string }) {
  const course = useCourse(slug);
  const lesson = useLesson(lessonId);

  if (course.isError || lesson.isError)
    return <ErrorState error={course.error ?? lesson.error} onRetry={() => (course.refetch(), lesson.refetch())} />;

  return (
    <div className="grid gap-6 lg:grid-cols-[240px_1fr_320px]">
      <aside className="hidden lg:block">
        <Link href={`/teach/${slug}`} className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:underline">
          <ArrowLeft className="size-4" aria-hidden /> {course.data?.title ?? "Khóa học"}
        </Link>
        {course.data ? <EditorOutline course={course.data} slug={slug} lessonId={lessonId} /> : <Skeleton className="h-60" />}
      </aside>
      {lesson.isPending ? (
        <div className="space-y-4" aria-busy="true" aria-label="Đang tải">
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : (
        <>
          <Content key={lesson.data.id} lesson={lesson.data} slug={slug} />
          <div className="space-y-8">
            <VideoBox lessonId={lessonId} />
            <SourceList lessonId={lessonId} />
          </div>
        </>
      )}
    </div>
  );
}

/** Mục lục trong trình soạn: các link trỏ về trình soạn bài, không phải trang học. */
function EditorOutline({ course, slug, lessonId }: { course: Parameters<typeof CourseOutline>[0]["course"]; slug: string; lessonId: string }) {
  return (
    <CourseOutline course={course} currentLessonId={lessonId} hrefFor={(id) => `/teach/${slug}/lessons/${id}`} />
  );
}

function Content({ lesson, slug }: { lesson: LessonDetail; slug: string }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [value, setValue] = React.useState({ title: lesson.title, content_md: lesson.content_md });
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const titleEmpty = !value.title.trim();
  const autosave = useAutosave(
    value,
    async (v) => {
      await unwrap(
        api.PATCH("/api/v1/lessons/{lesson_id}", {
          params: { path: { lesson_id: lesson.id } },
          body: { title: v.title.trim(), content_md: v.content_md },
        }),
      );
      qc.setQueryData<LessonDetail>(qk.lesson(lesson.id), (old) => (old ? { ...old, ...v } : old));
      if (v.title !== lesson.title) qc.invalidateQueries({ queryKey: qk.course(slug) });
    },
    { enabled: !titleEmpty },
  );

  // rời trang khi còn thay đổi chưa lưu → trình duyệt hỏi lại
  React.useEffect(() => {
    const dirty = autosave.state.status === "dirty" || autosave.state.status === "saving";
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [autosave.state.status]);

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/teach/${slug}`} className="flex items-center gap-1 text-sm text-muted-foreground hover:underline lg:hidden">
          <ArrowLeft className="size-4" aria-hidden /> Về khóa học
        </Link>
        <span aria-live="polite" className="ml-auto text-sm text-muted-foreground">
          {autosaveLabel(autosave.state)}
        </span>
        <Button variant="outline" size="sm" className="h-10 md:h-8" onClick={() => void autosave.flush()} disabled={titleEmpty}>
          <Save /> Lưu
        </Button>
        <Button asChild variant="outline" size="sm" className="h-10 md:h-8">
          <Link href={`/learn/${slug}/${lesson.id}`}>
            <Eye /> Xem như học viên
          </Link>
        </Button>
      </div>

      <Field id="l-title" label="Tên bài" error={titleEmpty ? "Tên bài không được trống" : undefined}>
        <Input value={value.title} maxLength={200} onChange={(e) => setValue((v) => ({ ...v, title: e.target.value }))} />
      </Field>

      <Tabs.Root defaultValue="write">
        <Tabs.List aria-label="Nội dung bài" className="inline-flex rounded-md border p-0.5">
          {[
            ["write", "Soạn"],
            ["preview", "Xem trước"],
          ].map(([v, l]) => (
            <Tabs.Trigger
              key={v}
              value={v}
              className="h-9 rounded px-3 text-sm data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
            >
              {l}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="write" className="mt-3">
          <label htmlFor="l-content" className="sr-only">
            Nội dung bài (markdown)
          </label>
          <textarea
            id="l-content"
            value={value.content_md}
            maxLength={100_000}
            onChange={(e) => setValue((v) => ({ ...v, content_md: e.target.value }))}
            placeholder={"# Tiêu đề\n\nNội dung markdown. Công thức: $E = mc^2$"}
            className="min-h-[60dvh] w-full rounded-md border bg-surface p-4 font-mono text-sm leading-relaxed"
          />
          <p className="mt-1 text-xs text-muted-foreground">Hỗ trợ Markdown, bảng, công thức LaTeX ($…$ và $$…$$). Tự lưu sau 1 giây ngừng gõ.</p>
        </Tabs.Content>
        <Tabs.Content value="preview" className="mt-3 rounded-md border bg-surface p-4 md:p-6">
          {value.content_md ? <Markdown>{value.content_md}</Markdown> : <p className="text-muted-foreground">Chưa có nội dung.</p>}
        </Tabs.Content>
      </Tabs.Root>

      <div className="border-t pt-4">
        <Button variant="destructive-outline" onClick={() => setDeleteOpen(true)}>
          <Trash2 /> Xóa bài này
        </Button>
      </div>
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        destructive
        title={`Xóa bài “${lesson.title}”?`}
        description="Nội dung, video, tài liệu PDF và tiến độ học của bài sẽ bị xóa và không khôi phục được."
        confirmLabel="Xóa bài"
        pendingLabel="Đang xóa…"
        onConfirm={async () => {
          try {
            await unwrap(api.DELETE("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: lesson.id } } }));
            qc.invalidateQueries({ queryKey: qk.course(slug) });
            toast.success("Đã xóa bài");
            router.replace(`/teach/${slug}`);
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </div>
  );
}

function VideoBox({ lessonId }: { lessonId: string }) {
  const qc = useQueryClient();
  const video = useLessonVideo(lessonId);
  const [removeOpen, setRemoveOpen] = React.useState(false);

  const patch = (body: { video_asset_id: string | null; duration_sec: number | null }) =>
    unwrap(api.PATCH("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: lessonId } }, body }));
  const refresh = () => {
    qc.invalidateQueries({ queryKey: qk.lessonVideo(lessonId) });
    qc.invalidateQueries({ queryKey: ["course"] });
  };

  return (
    <section aria-labelledby="video-title" className="space-y-3">
      <h2 id="video-title" className="font-semibold">
        Video bài giảng
      </h2>
      {video.isPending ? (
        <Skeleton className="aspect-video w-full" />
      ) : video.data ? (
        <>
          <video src={video.data} controls preload="metadata" className="aspect-video w-full rounded-md bg-black" />
          <Button variant="destructive-outline" size="sm" className="h-10 md:h-8" onClick={() => setRemoveOpen(true)}>
            <Trash2 /> Gỡ video
          </Button>
        </>
      ) : null}
      <FileDrop
        kind="video"
        label={video.data ? "Thay video khác" : "Chọn file MP4"}
        onUploaded={async (assetId, file) => {
          const duration = await readVideoDuration(file);
          await patch({ video_asset_id: assetId, duration_sec: duration });
          refresh();
          toast.success("Đã gắn video vào bài");
        }}
      />
      <ConfirmDialog
        open={removeOpen}
        onOpenChange={setRemoveOpen}
        destructive
        title="Gỡ video khỏi bài?"
        description="Học viên sẽ không xem được video này nữa."
        confirmLabel="Gỡ video"
        pendingLabel="Đang gỡ…"
        onConfirm={async () => {
          try {
            await patch({ video_asset_id: null, duration_sec: null });
            refresh();
            toast.success("Đã gỡ video");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </section>
  );
}
```

`src/app/(main)/teach/[slug]/lessons/[lessonId]/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { LessonEditor } from "@/components/teach/lesson-editor";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function LessonEditorPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth staff>
      <LessonEditor slug={slug} lessonId={lessonId} />
    </RequireAuth>
  );
}
```

- [ ] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test && npm run build
git add frontend/src && git commit -m "feat(web): lesson editor with autosave, video and PDF sources"
```

Expected: build liệt kê 12 route, gồm `ƒ /teach/[slug]/lessons/[lessonId]`.

---

## Task 16: E2E ở 375px và 1280px, kèm kiểm tra khả năng truy cập

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/e2e/mock-api.ts`, `frontend/e2e/a11y.ts`, `frontend/e2e/student.spec.ts`, `frontend/e2e/teacher.spec.ts`

E2E dùng **API giả** (`page.route`) nên chạy được trên CI mà không cần backend, DB hay Gemini. Cách bố trí:

- `webServer` build với `API_ORIGIN=http://127.0.0.1:9` (một cổng không có gì chạy). Request nào chưa được mock sẽ fail rõ ràng với lỗi `UNMOCKED`.
- Mỗi kịch bản chạy ở 2 project: `mobile-375` và `desktop-1280`.
- Mỗi kịch bản kiểm tra axe (WCAG 2.1 AA) và kiểm tra không có cuộn ngang.

- [ ] **Bước 1: Cài trình duyệt cho Playwright**

```bash
npx playwright install chromium
```

(Trên Linux/CI dùng `npx playwright install --with-deps chromium`. Nếu máy đã có sẵn Chromium khác phiên bản thì đặt `PW_CHROMIUM=<đường dẫn chrome>`.)

- [ ] **Bước 2: Cấu hình**

`playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 3100);

// E2E chạy với API giả (page.route trong e2e/mock-api.ts) nên không cần backend/Gemini.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    locale: "vi-VN",
    // Máy đã có sẵn Chromium khác phiên bản thì trỏ tới đó: PW_CHROMIUM=/đường/dẫn/chrome
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  projects: [
    { name: "mobile-375", use: { ...devices["Pixel 7"], viewport: { width: 375, height: 812 } } },
    { name: "desktop-1280", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    command: `npm run build && npx next start -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    // API_ORIGIN trỏ vào cổng không có gì: mọi request /api/v1 phải được mock, lọt ra là lỗi
    env: { API_ORIGIN: "http://127.0.0.1:9" },
  },
});
```

`e2e/mock-api.ts`:

```ts
import type { Page, Route } from "@playwright/test";

export const COURSE_ID = "11111111-1111-1111-1111-111111111111";
export const SECTION_ID = "22222222-2222-2222-2222-222222222222";
export const L1 = "33333333-3333-3333-3333-333333333331";
export const L2 = "33333333-3333-3333-3333-333333333332";

export const student = { id: "u-1", email: "an@sv.vn", full_name: "Nguyễn Văn An", role: "student", teacher_status: null };
export const teacher = { id: "u-2", email: "gv@lms.vn", full_name: "Trần Thị Bình", role: "teacher", teacher_status: "approved" };

export const courseDetail = (over: Record<string, unknown> = {}) => ({
  id: COURSE_ID,
  teacher_id: "u-2",
  title: "Giải tích 1",
  slug: "giai-tich-1",
  description: "Giới hạn, **đạo hàm** và tích phân.",
  status: "published",
  created_at: "2026-09-01T00:00:00Z",
  teacher_name: "Trần Thị Bình",
  is_enrolled: false,
  is_owner: false,
  sections: [
    {
      id: SECTION_ID,
      title: "Đạo hàm",
      position: 0,
      lessons: [
        { id: L1, title: "Định nghĩa đạo hàm", position: 0, duration_sec: 600 },
        { id: L2, title: "Quy tắc tính đạo hàm", position: 1, duration_sec: null },
      ],
    },
  ],
  ...over,
});

export const lesson = (id = L1) => ({
  id,
  section_id: SECTION_ID,
  course_id: COURSE_ID,
  title: id === L1 ? "Định nghĩa đạo hàm" : "Quy tắc tính đạo hàm",
  content_md: "## Định nghĩa\n\nĐạo hàm của $f$ tại $x_0$ là giới hạn:\n\n$$f'(x_0)=\\lim_{h\\to 0}\\frac{f(x_0+h)-f(x_0)}{h}$$\n\n".repeat(3),
  duration_sec: null,
  progress: null,
});

type Handler = (route: Route, url: URL) => Promise<void> | void;

const json = (route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body), headers });
const err = (route: Route, status: number, code: string, message: string) =>
  json(route, { error: { code, message, details: {}, request_id: "rq-e2e" } }, status);

/**
 * Mock toàn bộ /api/v1. `user` = null nghĩa là khách (refresh trả 401).
 * `extra` ghi đè/thêm handler theo "METHOD /đường-dẫn" (đường dẫn sau /api/v1, có thể dùng *).
 */
export async function mockApi(page: Page, opts: { user?: typeof student | typeof teacher | null; extra?: Record<string, Handler> } = {}) {
  const user = opts.user === undefined ? student : opts.user;
  const handlers: Record<string, Handler> = {
    "POST /auth/refresh": (r) => (user ? json(r, { access_token: "tok", token_type: "bearer" }) : err(r, 401, "INVALID_TOKEN", "x")),
    "POST /auth/login": (r) => json(r, { access_token: "tok", token_type: "bearer" }),
    "POST /auth/logout": (r) => r.fulfill({ status: 204 }),
    "GET /me": (r) => (user ? json(r, user) : err(r, 401, "NOT_AUTHENTICATED", "Bạn cần đăng nhập")),
    "GET /courses": (r) =>
      json(r, {
        items: [{ id: COURSE_ID, title: "Giải tích 1", slug: "giai-tich-1", description: "Giới hạn, đạo hàm và tích phân.", teacher_name: "Trần Thị Bình" }],
        total: 1,
        page: 1,
        size: 12,
      }),
    "GET /courses/giai-tich-1": (r) => json(r, courseDetail({ is_enrolled: user?.role === "student", is_owner: user?.role === "teacher" })),
    "GET /me/courses": (r) =>
      json(r, {
        items: [{ course_id: COURSE_ID, title: "Giải tích 1", slug: "giai-tich-1", enrolled_at: "2026-09-02T00:00:00Z", completed_at: null, total_lessons: 2, done_lessons: 1, progress_pct: 50 }],
        total: 1,
        page: 1,
        size: 20,
      }),
    [`GET /lessons/${L1}`]: (r) => json(r, lesson(L1)),
    [`GET /lessons/${L2}`]: (r) => json(r, lesson(L2)),
    "GET /lessons/*/video": (r) => err(r, 404, "NOT_FOUND", "Video không tồn tại"),
    "PUT /lessons/*/progress": (r) => json(r, { status: "done", video_position_sec: 0, completed_at: "2026-10-01T00:00:00Z" }),
    "GET /tutor/availability": (r) => json(r, { available: true, ready_chunks: 12, message: null }),
    "GET /tutor/sessions": (r) => json(r, { items: [], total: 0, page: 1, size: 20 }),
    "POST /tutor/sessions": (r) => json(r, { id: "s-1", course_id: COURSE_ID, lesson_id: L1, created_at: "2026-10-01T00:00:00Z" }, 201),
    "POST /tutor/sessions/s-1/messages": (r) => {
      const src = { n: 1, chunk_id: "k1", lesson_id: L1, page_no: 4, start_sec: null, lesson_title: "Định nghĩa đạo hàm", heading_path: "Giáo trình › Chương 2", snippet: "Đạo hàm là giới hạn của tỉ số gia số…" };
      const events = [
        ["sources", { sources: [src] }],
        ["token", { text: "Đạo hàm là giới hạn của tỉ số gia số " }],
        ["token", { text: "khi h tiến về 0 [1]." }],
        ["done", { message_id: "m-1", content: "Đạo hàm là giới hạn của tỉ số gia số khi h tiến về 0 [1].", citations: [src], refused: false }],
      ];
      return r.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(""),
      });
    },
    "POST /tutor/messages/*/feedback": (r) => json(r, {}),
    ...opts.extra,
  };

  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = route.request().method();
    const key = Object.keys(handlers).find((k) => {
      const [m, p] = k.split(" ");
      if (m !== method) return false;
      const re = new RegExp(`^${p.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^/]+")}$`);
      return re.test(path);
    });
    if (!key) return err(route, 500, "UNMOCKED", `Chưa mock ${method} ${path}`);
    await handlers[key](route, url);
  });
}
```

`e2e/a11y.ts`:

```ts
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/** Kiểm tra WCAG 2.1 AA bằng axe; lỗi nào cũng in rõ id + phần tử để sửa. */
export async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const summary = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(summary).toEqual([]);
}

/** Không có cuộn ngang (design-system §9). */
export async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}
```

- [ ] **Bước 3: Kịch bản học viên** (`e2e/student.spec.ts`)

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { L1, L2, mockApi } from "./mock-api";

test.describe("học viên", () => {
  test("khách xem catalog → chi tiết → bấm Đăng ký thì được chuyển tới đăng nhập", async ({ page }) => {
    await mockApi(page, { user: null });
    await page.goto("/explore");
    await expect(page.getByRole("heading", { name: "Khám phá khóa học" })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByRole("link", { name: /Giải tích 1/ }).click();
    await expect(page.getByRole("heading", { name: "Giải tích 1", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "Đăng ký khóa học" }).click();
    await expect(page).toHaveURL(/\/login\?next=%2Fcourses%2Fgiai-tich-1/);
  });

  test("đăng nhập sai mật khẩu báo lỗi ngay dưới ô và giữ con trỏ ở đó", async ({ page }) => {
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/login": (r) =>
          r.fulfill({ status: 401, json: { error: { code: "INVALID_CREDENTIALS", message: "Email hoặc mật khẩu không đúng", details: {}, request_id: null } } }),
      },
    });
    await page.goto("/login");
    await page.getByLabel("Email").fill("an@sv.vn");
    await page.getByLabel("Mật khẩu").fill("sai-mat-khau");
    await page.getByRole("button", { name: "Đăng nhập" }).click();
    await expect(page.getByText("Email hoặc mật khẩu không đúng")).toBeVisible();
    await expect(page.getByLabel("Mật khẩu")).toBeFocused();
    await expectAccessible(page);
  });

  test("trang chủ học viên hiện khóa của tôi với tiến độ", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByText("1/2 bài · 50%")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("học bài: đọc, hỏi AI có trích nguồn, đánh dấu xong, sang bài tiếp", async ({ page, isMobile }) => {
    await mockApi(page);
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await expect(page.getByRole("heading", { name: "Định nghĩa đạo hàm", level: 1 })).toBeVisible();
    await expect(page.locator(".katex").first()).toBeVisible();
    await expectNoHorizontalScroll(page);
    await expectAccessible(page);

    // Hỏi AI: desktop mở panel phải, điện thoại mở khung trượt
    await page.getByRole("button", { name: "Hỏi AI" }).first().click();
    const input = page.getByLabel("Câu hỏi cho AI Tutor");
    await input.fill("Đạo hàm là gì?");
    await input.press("Enter");
    await expect(page.getByText(/tiến về 0/)).toBeVisible();
    await page.getByRole("button", { name: /Nguồn 1, trang 4/ }).click();
    await expect(page.getByText("Đạo hàm là giới hạn của tỉ số gia số…")).toBeVisible();
    await page.keyboard.press("Escape"); // đóng popover nguồn
    await page.keyboard.press("Escape"); // đóng panel
    if (isMobile) await expect(page.getByRole("dialog", { name: "AI Tutor" })).toBeHidden();

    await page.getByRole("button", { name: "Đánh dấu đã học xong" }).click();
    await expect(page.getByText("Đã học xong bài này")).toBeVisible();
    await page.getByRole("button", { name: /Bài tiếp: Quy tắc tính đạo hàm/ }).click();
    await expect(page).toHaveURL(new RegExp(L2));
  });

  test("AI quá tải (429) → báo số giây và khóa nút Gửi đếm ngược", async ({ page }) => {
    await mockApi(page, {
      extra: {
        "POST /tutor/sessions/s-1/messages": (r) =>
          r.fulfill({
            status: 429,
            headers: { "Retry-After": "30" },
            json: { error: { code: "RATE_LIMITED", message: "Chậm lại", details: {}, request_id: null } },
          }),
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await page.getByRole("button", { name: "Hỏi AI" }).first().click();
    await page.getByLabel("Câu hỏi cho AI Tutor").fill("Hỏi nhanh");
    await page.getByLabel("Câu hỏi cho AI Tutor").press("Enter");
    await expect(page.getByText(/thử lại sau 30 giây/)).toBeVisible();
    await expect(page.getByRole("button", { name: /\d+s/ })).toBeDisabled();
  });
});

test("trang bài học đạt chuẩn tương phản ở cả 3 chế độ màu", async ({ page }) => {
  await mockApi(page);
  for (const theme of ["light", "dark", "sepia"]) {
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await expect(page.locator("html")).toHaveClass(new RegExp(theme === "light" ? "light" : theme));
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectAccessible(page);
  }
});
```

- [ ] **Bước 4: Kịch bản giảng viên** (`e2e/teacher.spec.ts`)

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { courseDetail, L1, L2, mockApi, SECTION_ID, teacher } from "./mock-api";

const draft = courseDetail({ status: "draft", is_owner: true });

test.describe("giảng viên", () => {
  test("trình soạn: sắp xếp bằng nút ↑↓ gửi đúng thứ tự, xuất bản cần xác nhận", async ({ page }) => {
    let reorderBody: unknown = null;
    let published = false;
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: published ? { ...draft, status: "published" } : draft }),
        "PATCH /courses/*/reorder": (r) => {
          reorderBody = r.request().postDataJSON();
          return r.fulfill({ status: 204 });
        },
        "POST /courses/*/publish": (r) => {
          published = true;
          return r.fulfill({ json: { ...draft, status: "published" } });
        },
      },
    });
    await page.goto("/teach/giai-tich-1");
    await expect(page.getByText("Nháp")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByRole("button", { name: "Đưa bài Quy tắc tính đạo hàm lên" }).click();
    await expect.poll(() => reorderBody).toEqual({ sections: [{ id: SECTION_ID, lesson_ids: [L2, L1] }] });

    await page.getByRole("button", { name: "Xuất bản" }).click();
    const dialog = page.getByRole("alertdialog", { name: "Xuất bản khóa học?" });
    await expect(dialog.getByRole("button", { name: "Hủy" })).toBeFocused(); // Hủy được focus sẵn
    await dialog.getByRole("button", { name: "Xuất bản" }).click();
    await expect(page.getByText("Đã xuất bản")).toBeVisible();
  });

  test("xóa khóa học phải gõ lại đúng tên", async ({ page }) => {
    await mockApi(page, { user: teacher, extra: { "GET /courses/giai-tich-1": (r) => r.fulfill({ json: draft }) } });
    await page.goto("/teach/giai-tich-1");
    await page.getByRole("button", { name: "Xóa khóa học" }).click();
    const dialog = page.getByRole("alertdialog");
    const confirm = dialog.getByRole("button", { name: "Xóa vĩnh viễn" });
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel(/Gõ/).fill("Giải tích 1");
    await expect(confirm).toBeEnabled();
  });

  test("soạn bài: tự lưu nội dung và hiện 'Đã lưu lúc'", async ({ page }) => {
    let saved: Record<string, unknown> | null = null;
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: draft }),
        "GET /lessons/*/sources": (r) => r.fulfill({ json: [] }),
        "PATCH /lessons/*": (r) => {
          saved = r.request().postDataJSON();
          return r.fulfill({ json: { id: L1, section_id: SECTION_ID, title: "x", position: 0, content_md: "", duration_sec: null, video_asset_id: null } });
        },
      },
    });
    await page.goto(`/teach/giai-tich-1/lessons/${L1}`);
    await page.getByLabel("Nội dung bài (markdown)").fill("# Mới\n\nNội dung mới");
    await expect(page.getByText(/Đã lưu lúc/)).toBeVisible();
    expect(saved).toMatchObject({ content_md: "# Mới\n\nNội dung mới" });
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });
});
```

- [ ] **Bước 5: Chạy**

Run: `npm run e2e`
Expected: `18 passed`. Lần đầu mất khoảng 1–2 phút vì phải build.

Nếu axe báo lỗi, test in ra `"<rule-id>: <selector>"`. Sửa đúng phần tử đó, **không tắt rule**. Ví dụ gặp khi viết plan: `link-in-text-block` với link "Đăng ký" chỉ phân biệt bằng màu, sửa bằng cách thêm gạch chân.

- [ ] **Bước 6: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e && git commit -m "test(web): Playwright E2E at 375/1280 with axe checks"
```

---

## Task 17: Docker, compose và CI cho frontend

**Files:**
- Create: `frontend/Dockerfile`, `frontend/.dockerignore`
- Modify: `docker-compose.yml` (thêm service `web`), `.github/workflows/ci.yml` (thêm job `frontend` và build image web)

- [ ] **Bước 1: `frontend/Dockerfile`** (standalone, chạy bằng user thường)

```dockerfile
# syntax=docker/dockerfile:1
# Build Next.js ở chế độ standalone: image chạy chỉ cần node + thư mục .next/standalone.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
# Rewrites /api/v1 → API được "đóng băng" lúc build, nên địa chỉ API là build arg.
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=$API_ORIGIN NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1
CMD ["node", "server.js"]
```

`frontend/.dockerignore`:

```text
node_modules
.next
coverage
test-results
playwright-report
.env*
```

- [ ] **Bước 2: Thêm service `web` vào `docker-compose.yml`** (đặt sau service `worker`)

```yaml
  web:
    # Chạy cả frontend trong Docker: docker compose --profile web up -d --build
    # (khi phát triển thường chạy `npm run dev` ngoài Docker cho nhanh).
    profiles: ["web"]
    build:
      context: ./frontend
      args:
        API_ORIGIN: http://api:8000
    ports: ["127.0.0.1:3000:3000", "[::1]:3000:3000"]
    depends_on:
      - api
```

- [ ] **Bước 3: Thêm job vào `.github/workflows/ci.yml`**

Job mới `frontend`. Đặt ngang hàng với `lint`, `test`, `docker`. Job có `defaults` riêng vì `defaults` gốc của file là `backend`:

```yaml
  frontend:
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
```

Trong job `docker` có sẵn, thêm bước build image web ngay sau bước build backend:

```yaml
      - name: Build frontend image (không push)
        uses: docker/build-push-action@v6
        with:
          context: frontend
          push: false
          build-args: API_ORIGIN=http://api:8000
          cache-from: type=gha,scope=web
          cache-to: type=gha,mode=max,scope=web
```

- [ ] **Bước 4: Kiểm tra local**

```bash
docker compose --profile web up -d --build
```

Mở `http://localhost:3000`, thấy trang chủ. Đăng nhập bằng tài khoản thật vẫn hoạt động, vì `/api/v1` được chuyển tới service `api`.

- [ ] **Bước 5: Commit, push và xem CI**

```bash
git add frontend/Dockerfile frontend/.dockerignore docker-compose.yml .github/workflows/ci.yml
git commit -m "ci(web): frontend lint/test/e2e job, Docker image and compose service"
git push
```

Expected: trên GitHub Actions, cả 4 job (`lint`, `test`, `frontend`, `docker`) đều xanh.

> **Ghi chú cho plan tầng S (Task 9, Caddy):** khi deploy, Caddy định tuyến `/api/*` → `api:8000` và mọi đường dẫn khác → `web:3000`. Thay trang giữ chỗ bằng `reverse_proxy web:3000`. Rewrite của Next vẫn còn nhưng khi đó không còn được dùng.

---

## Task 18: Kiểm tra cuối với backend thật và cập nhật spec

**Files:**
- Modify: `docs/specs/2026-09-29-lms-ai-design.md` (bảng tiến độ và nhật ký quyết định)

- [ ] **Bước 1: Bộ kiểm tra tự động**

```bash
npm run lint && npm run typecheck && npm test && npm run build && npm run e2e
```

Expected: tất cả PASS. Có 46 unit test và 18 test E2E.

- [ ] **Bước 2: Chạy thật với backend** (2 terminal)

```bash
# terminal 1, ở thư mục gốc repo
docker compose up -d --build
# terminal 2
cd frontend && npm run dev
```

Mở `http://localhost:3000` và làm lần lượt (đánh dấu từng dòng khi đạt):

- [ ] Đăng ký giảng viên → thấy thông báo chờ duyệt. Duyệt tài khoản bằng `docker compose exec api python -m app.scripts.approve_teacher <email>`, sau đó đăng nhập lại thì thấy mục "Khóa đang dạy".
- [ ] Tạo khóa → thêm 1 chương, 2 bài → soạn nội dung có công thức `$x^2$` → thấy "Đã lưu lúc …" → tab Xem trước hiển thị công thức.
- [ ] Tải lên 1 file PDF → thanh % chạy → "Đang xử lý" → **"Sẵn sàng"** mà không phải tải lại trang → "Xem các trang đã trích" mở được. *Nếu PUT lên MinIO bị lỗi CORS trong DevTools, kiểm tra biến môi trường CORS của MinIO, mặc định là cho phép mọi origin.*
- [ ] Tải lên 1 video MP4 → video phát được trong trình soạn.
- [ ] Đổi thứ tự 2 bài bằng ↑↓ và bằng kéo thả → tải lại trang vẫn giữ thứ tự mới.
- [ ] Xuất bản → đăng xuất → đăng ký học viên → khóa hiện ở Khám phá → Đăng ký → vào bài 1.
- [ ] Xem video 30 giây rồi chuyển sang bài khác, quay lại → video tiếp tục từ khoảng giây 30. Cuộn nửa bài, tải lại trang → về đúng chỗ.
- [ ] Hỏi AI (với `LLM_PROVIDER=gemini`, nếu đã cấu hình) → nguồn hiện trước, chữ chạy dần, chip `[1]` mở được thẻ trích dẫn. Bấm **Dừng** giữa chừng → có dòng "Đã dừng". Tải lại trang, mở lại Tutor → lịch sử vẫn còn.
- [ ] Trong DevTools → Network, câu trả lời Tutor hiện **từng phần** chứ không đợi xong mới hiện hết, tức là rewrite của `next dev` không giữ lại luồng. Nếu thấy bị dồn lại, đặt `NEXT_PUBLIC_API_BASE=http://localhost:8000` trong `.env.local` để gọi API trực tiếp. Backend đã cho phép CORS từ `localhost:3000`.
- [ ] Đổi 3 chế độ màu, chỉnh A− / A+, bấm `F`, `/`, `←`, `→`, `?` → đều hoạt động. Chuyển DevTools sang 375px → không có cuộn ngang, Tutor mở dạng khung trượt.
- [ ] Giảng viên xóa một bài đã có học viên học → hộp thoại vẫn mở và hiện thông báo 409 của backend.
- [ ] Lighthouse (Chrome DevTools, chế độ Navigation, Mobile) cho `/explore` và một trang bài học: ghi lại điểm Performance, Accessibility, Best Practices vào `docs/eval/lighthouse-fe1.md`. Mục tiêu mỗi điểm ≥ 90.

- [ ] **Bước 3: Cập nhật spec**

Trong `docs/specs/2026-09-29-lms-ai-design.md`:

- Bảng tiến độ: đánh dấu xong các mục frontend của A (trang học, Tutor UI, trình soạn, upload).
- Ghi chú: "FE-2 (quiz, duyệt câu hỏi, dashboard) chưa làm".
- Thêm vào nhật ký quyết định (mục 13):

```markdown
| 2026-10-04 | Frontend gọi API cùng origin qua Next rewrites (cookie refresh không cần CORS); type sinh từ OpenAPI, CI chặn lệch type. Font đóng gói bằng Fontsource thay vì Google Fonts (build offline, không gửi request ra ngoài). Chip trích dẫn mở thẻ đoạn trích thay vì cuộn tới đoạn trong bài, vì nguồn RAG là PDF. |
```

- [ ] **Bước 4: Commit**

```bash
git add docs && git commit -m "docs: FE-1 done, update spec progress and decisions"
```

---

## Phụ lục A: Ánh xạ yêu cầu → task

| Yêu cầu (spec / design-system) | Task |
|---|---|
| 3 chế độ màu, token màu, khung đọc 17px / 1.75 / 68 ký tự | 2, 8, 13 |
| 5 loại nút, cỡ, trạng thái đang xử lý | 3 |
| Bảng hành động → nút của học viên (đăng ký, học tiếp, đánh dấu xong, bài trước/sau, Hỏi AI, tập trung, A−/A+, Gửi/Dừng, nguồn, 👍👎, Thử lại) | 10, 12, 13 |
| Bảng hành động → nút của giảng viên (tạo khóa, thêm chương/bài, tự lưu, kéo thả + ↑↓, xem trước, xuất bản, xóa, tải PDF, xử lý lại, xem trang đã trích) | 14, 15 |
| Phần Chung (đăng nhập/đăng ký, đăng xuất tách riêng, nhóm chọn chế độ màu) | 8, 9 |
| 4 trạng thái mỗi màn hình, toast, hộp xác nhận, 429 đếm ngược | 3, 8, 12 |
| Điều hướng desktop / tablet / điện thoại | 8 |
| Học tiếp đúng chỗ, nhắc nghỉ mắt, phím tắt | 10, 11, 13 |
| Responsive 375 / 1280, WCAG AA, không cuộn ngang | 16 |
| Phản hồi realtime: % upload, trạng thái xử lý, Tutor stream | 6, 12, 15 |
| Lighthouse ≥ 90 (spec 9.8) | 18 |
| CI, Docker | 17 |

**Để lại cho FE-2** (backend đã có API):

- Sinh và duyệt câu hỏi, gồm mục "Câu hỏi chờ duyệt" trên thanh bên của giảng viên.
- Quiz: làm bài, tự lưu đáp án, nộp bài, kết quả. Nhắc nghỉ mắt truyền `paused` khi quiz có giờ.
- Dashboard analytics của giảng viên.
- Trang "Duyệt giảng viên" cho admin. Hiện tại admin duyệt bằng script `approve_teacher`.

## Phụ lục B: Lỗi hay gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Đăng nhập xong, F5 là bị đăng xuất | Cookie refresh không về tới server: đang gọi API khác origin mà không có `credentials`, hoặc `NEXT_PUBLIC_API_BASE` trỏ sai | Bỏ `NEXT_PUBLIC_API_BASE` để dùng rewrite cùng origin |
| `TOKEN_REUSED` khi mở nhiều tab | 2 tab cùng refresh với một cookie cũ | Bình thường: một tab sẽ bị đăng xuất. Đăng nhập lại |
| `npm i` báo ERESOLVE về `@types/node` | Vitest 5 cần `@types/node` ≥ 22 | `npm i -D @types/node@^22` |
| Production gọi `/api/v1` bị 500 ECONNREFUSED | `API_ORIGIN` sai lúc **build** (rewrite bị đóng băng lúc build) | Build lại với `--build-arg API_ORIGIN=…` |
| `tsc` báo lỗi type ở `api.GET(...)` sau khi backend đổi | `schema.d.ts` đã cũ | `npm run gen:api` |
| Test autosave làm worker bị SIGKILL | Vòng lặp lưu không dừng khi lỗi | Xem lại `run()` trong `use-autosave.ts` |
