import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { courseDetail, L1, mockApi, teacher } from "./mock-api";

const AS_ID = "44444444-4444-4444-4444-444444444441";
const SUB_ID = "55555555-5555-5555-5555-555555555551";

const assignment = (over: Record<string, unknown> = {}) => ({
  id: AS_ID,
  lesson_id: L1,
  lesson_title: "Định nghĩa đạo hàm",
  course_slug: "giai-tich-1",
  title: "Tính đạo hàm bằng định nghĩa",
  instructions: "Dùng định nghĩa giới hạn để tính đạo hàm của $f(x) = x^2$ tại $x = 3$.",
  due_at: null,
  rubric: [
    { key: "c1", criterion: "Lập đúng tỉ số gia số", max_points: 6, description: "Viết đúng (f(3+h) − f(3))/h" },
    { key: "c2", criterion: "Kết quả và trình bày", max_points: 4, description: "" },
  ],
  max_total: 10,
  status: "published",
  created_at: "2026-10-29T00:00:00Z",
  submission_count: null,
  to_review: null,
  my_submission: null,
  ...over,
});

test.describe("bài tập (B5)", () => {
  test("học viên thấy bài tập trong bài học, mở đề, nộp bài và thấy trạng thái chờ chấm", async ({ page }) => {
    let current = assignment();
    let sent: unknown = null;
    await mockApi(page, {
      extra: {
        "GET /assignments": (r) => r.fulfill({ json: { items: [current], total: 1, page: 1, size: 50 } }),
        [`GET /assignments/${AS_ID}`]: (r) => r.fulfill({ json: current }),
        [`PUT /assignments/${AS_ID}/submission`]: (r) => {
          sent = r.request().postDataJSON();
          const mine = {
            id: SUB_ID,
            version: 1,
            status: "submitted",
            submitted_at: new Date().toISOString(),
            text_content: "Tỉ số gia số là (9 + 6h + h² − 9)/h = 6 + h, cho h → 0 được 6.",
            file: null,
            final_scores: null,
            final_total: null,
            teacher_feedback: null,
            graded_at: null,
          };
          current = assignment({ my_submission: mine });
          return r.fulfill({ json: mine });
        },
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    const section = page.getByRole("region", { name: "Bài tập" });
    await expect(section.getByText("Chưa nộp")).toBeVisible();
    await section.getByRole("link", { name: "Làm bài" }).click();

    await expect(page.getByRole("heading", { name: "Tính đạo hàm bằng định nghĩa", level: 1 })).toBeVisible();
    await expect(page.getByText("Lập đúng tỉ số gia số")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByLabel("Bài làm").fill("Tỉ số gia số là (9 + 6h + h² − 9)/h = 6 + h, cho h → 0 được 6.");
    await page.getByRole("button", { name: "Nộp bài" }).click();
    await expect(page.getByRole("heading", { name: "Đã nộp bài" })).toBeVisible();
    expect(sent).toEqual({ text_content: "Tỉ số gia số là (9 + 6h + h² − 9)/h = 6 + h, cho h → 0 được 6.", asset_id: null });
    await expectAccessible(page);
  });

  test("giảng viên mở bài nộp từ thông báo, xem gợi ý của AI và xác nhận điểm", async ({ page }) => {
    let graded: unknown = null;
    const detail = (over: Record<string, unknown> = {}) => ({
      id: SUB_ID,
      assignment_id: AS_ID,
      user_id: "u-1",
      student_name: "Nguyễn Văn An",
      status: "ai_graded",
      version: 1,
      submitted_at: "2026-10-29T01:00:00Z",
      text_content: "Tỉ số gia số là (9 + 6h + h² − 9)/h = 6 + h, cho h → 0 được 6.",
      file: null,
      file_url: null,
      ai_result: {
        scores: {
          c1: { score: 5, justification: "Lập đúng tỉ số, thiếu bước rút gọn.", evidence_quote: "(9 + 6h + h² − 9)/h", evidence_found: true },
          c2: { score: 4, justification: "Kết quả đúng.", evidence_quote: "được 6", evidence_found: true },
        },
        feedback: "Bài làm đúng hướng, nên trình bày rõ bước rút gọn.",
        total: 9,
        model: "gemini",
        prompt_version: "assignment_grade@v1",
        version: 1,
      },
      ai_error: null,
      final_scores: null,
      final_total: null,
      teacher_feedback: null,
      graded_at: null,
      ...over,
    });
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: courseDetail({ is_owner: true }) }),
        [`GET /assignments/${AS_ID}`]: (r) => r.fulfill({ json: assignment({ submission_count: 1, to_review: 1 }) }),
        [`GET /assignments/${AS_ID}/submissions`]: (r) =>
          r.fulfill({
            json: {
              items: [
                {
                  id: SUB_ID,
                  user_id: "u-1",
                  student_name: "Nguyễn Văn An",
                  status: graded ? "graded" : "ai_graded",
                  version: 1,
                  submitted_at: "2026-10-29T01:00:00Z",
                  ai_total: 9,
                  final_total: graded ? 9.5 : null,
                  flagged: 0,
                },
              ],
              total: 1,
              page: 1,
              size: 20,
            },
          }),
        [`GET /submissions/${SUB_ID}`]: (r) => r.fulfill({ json: detail() }),
        [`POST /submissions/${SUB_ID}/grade`]: (r) => {
          graded = r.request().postDataJSON();
          return r.fulfill({ json: detail({ status: "graded", final_scores: { c1: 5.5, c2: 4 }, final_total: 9.5 }) });
        },
      },
    });
    await page.goto(`/teach/giai-tich-1/lessons/${L1}/assignments/${AS_ID}?bai=${SUB_ID}`);
    const panel = page.getByRole("region", { name: "Bài nộp của Nguyễn Văn An" });
    await expect(panel.getByText("AI gợi ý 5/6")).toBeVisible();
    await expect(panel.getByLabel("Điểm Lập đúng tỉ số gia số")).toHaveValue("5");
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await panel.getByLabel("Điểm Lập đúng tỉ số gia số").fill("5.5");
    await panel.getByRole("button", { name: "Xác nhận điểm" }).click();
    await expect(panel.getByRole("button", { name: "Cập nhật điểm" })).toBeVisible();
    expect(graded).toEqual({
      scores: { c1: 5.5, c2: 4 },
      feedback: "Bài làm đúng hướng, nên trình bày rõ bước rút gọn.",
    });
  });
});
