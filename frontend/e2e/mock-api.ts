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

export const STUDIO_KINDS = ["study_guide", "briefing", "faq", "timeline", "flashcards"] as const;

export const studioItem = (kind: string, over: Record<string, unknown> = {}) => ({
  kind,
  status: "none",
  artifact_id: null,
  job_id: null,
  error: null,
  stale: false,
  reviewed: false,
  created_at: null,
  ...over,
});

export const studioOverview = (over: Record<string, Record<string, unknown>> = {}, canRegenerate = false) => ({
  has_content: true,
  can_regenerate: canRegenerate,
  items: STUDIO_KINDS.map((k) => studioItem(k, over[k])),
});

export const note = (over: Record<string, unknown> = {}) => ({
  id: "n-1",
  course_id: COURSE_ID,
  lesson_id: L1,
  title: "Đạo hàm là gì?",
  content_md: "Đạo hàm là giới hạn của tỉ số gia số [1].",
  citations: [{ n: 1, chunk_id: "k1", lesson_id: L1, page_no: 4, start_sec: null, lesson_title: "Định nghĩa đạo hàm", heading_path: "Chương 2", snippet: "Đạo hàm là giới hạn…" }],
  status: "ready",
  from_message_id: "m-1",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  ...over,
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
    "GET /quizzes": (r) => json(r, { items: [], total: 0, page: 1, size: 50 }),
    "GET /courses/*/tutor-feedback": (r) => json(r, { items: [], total: 0, page: 1, size: 20 }),
    // AI Studio: mặc định chưa có gì (spec studio.spec.ts ghi đè khi cần)
    "GET /studio": (r) => json(r, studioOverview()),
    "GET /lessons/*/documents": (r) => json(r, []),
    "POST /tutor/messages/*/followups": (r) => json(r, { questions: [] }),
    "GET /notes": (r) => json(r, { items: [], total: 0, page: 1, size: 20 }),
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
