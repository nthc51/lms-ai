import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, courseDetail, L1, mockApi, teacher } from "./mock-api";
import { bankQuestion, quiz, QUIZ_ID } from "./quiz-data";

const course = courseDetail({ status: "published", is_owner: true });

test.describe("giảng viên: câu hỏi, quiz, thống kê", () => {
  test("sinh câu hỏi bằng AI (job nền) → duyệt một câu → loại một câu rồi hoàn tác", async ({ page }) => {
    let jobPolls = 0;
    let generated = false;
    const reviews: { id: string; action: string }[] = [];
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: course }),
        [`POST /lessons/${L1}/questions/generate`]: (r) => {
          expect(r.request().postDataJSON()).toEqual({ count: 10, difficulty: { easy: 0.3, medium: 0.5, hard: 0.2 } });
          return r.fulfill({ status: 202, json: { job_id: "job-1" } });
        },
        "GET /jobs/job-1": (r) => {
          jobPolls += 1;
          const done = jobPolls >= 2;
          if (done) generated = true;
          return r.fulfill({
            json: { id: "job-1", type: "quiz_gen", status: done ? "done" : "processing", attempts: 1, error_msg: null, finished_at: null },
          });
        },
        [`GET /lessons/${L1}/questions`]: (r) =>
          r.fulfill({
            json: {
              items: generated ? [bankQuestion("c1", "pending"), bankQuestion("c2", "pending", { self_check_flag: true })] : [],
              total: generated ? 2 : 0,
              page: 1,
              size: 100,
            },
          }),
        "PATCH /questions/*": (r, url) => {
          const id = url.pathname.split("/").pop()!;
          const body = r.request().postDataJSON();
          reviews.push({ id, action: body.action });
          return r.fulfill({ json: bankQuestion(id, body.action === "approve" ? "approved" : "rejected") });
        },
      },
    });

    await page.goto(`/teach/giai-tich-1/lessons/${L1}/questions`);
    await expect(page.getByRole("tab", { name: "Chờ duyệt (0)" })).toBeVisible();
    await page.getByRole("button", { name: "Sinh câu hỏi bằng AI" }).click();
    await expect(page.getByText(/AI đang soạn/)).toBeVisible();
    await expect(page.getByText("AI đã soạn xong. Có 2 câu chờ duyệt.")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("AI tự kiểm tra thấy nghi vấn")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByRole("button", { name: "Duyệt" }).first().click();
    await expect.poll(() => reviews).toEqual([{ id: "c1", action: "approve" }]);

    // Loại câu c2 rồi bấm Hoàn tác trong 5 giây → không gửi gì
    await page.getByRole("button", { name: "Loại" }).last().click();
    await page.getByRole("button", { name: "Hoàn tác" }).click();
    await page.waitForTimeout(5500);
    expect(reviews).toEqual([{ id: "c1", action: "approve" }]);
  });

  test("tạo quiz từ câu đã duyệt → xuất bản có xác nhận", async ({ page }) => {
    let created: Record<string, unknown> | null = null;
    let published = false;
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: course }),
        [`GET /lessons/${L1}/questions`]: (r) =>
          r.fulfill({ json: { items: [bankQuestion("c1", "approved"), bankQuestion("c2", "edited"), bankQuestion("c3", "pending")], total: 3, page: 1, size: 100 } }),
        "GET /quizzes": (r) =>
          r.fulfill({
            json: created
              ? { items: [quiz({ status: published ? "published" : "draft", question_count: 2, attempts_used: null })], total: 1, page: 1, size: 50 }
              : { items: [], total: 0, page: 1, size: 50 },
          }),
        "POST /quizzes": (r) => {
          created = r.request().postDataJSON();
          return r.fulfill({ status: 201, json: quiz({ status: "draft", question_count: 2 }) });
        },
        [`POST /quizzes/${QUIZ_ID}/publish`]: (r) => {
          published = true;
          return r.fulfill({ json: quiz() });
        },
      },
    });

    await page.goto(`/teach/giai-tich-1/lessons/${L1}/quizzes`);
    await page.getByRole("button", { name: "Tạo quiz" }).click();
    const dialog = page.getByRole("dialog", { name: "Tạo quiz" });
    await expect(dialog.getByText("Câu hỏi đã duyệt (0/2 được chọn)")).toBeVisible(); // câu chờ duyệt không được chọn
    await dialog.getByLabel("Tiêu đề").fill("Kiểm tra đạo hàm cơ bản");
    for (const cb of await dialog.getByRole("checkbox").all()) await cb.check();
    await dialog.getByRole("button", { name: "Tạo quiz" }).click();
    await expect.poll(() => created).toMatchObject({ lesson_id: L1, title: "Kiểm tra đạo hàm cơ bản", question_ids: ["c1", "c2"] });

    await page.getByRole("button", { name: "Xuất bản" }).click();
    const confirm = page.getByRole("alertdialog");
    await expect(confirm.getByRole("button", { name: "Hủy" })).toBeFocused();
    await confirm.getByRole("button", { name: "Xuất bản" }).click();
    await expect(page.getByText("Đã xuất bản", { exact: true })).toBeVisible();
    await expectAccessible(page);
  });

  test("trang thống kê hiện số liệu khóa, tỉ lệ hoàn thành và quiz", async ({ page }) => {
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: course }),
        [`GET /courses/${COURSE_ID}/analytics`]: (r) =>
          r.fulfill({
            json: {
              course_id: COURSE_ID,
              enrollments: 12,
              completed_enrollments: 3,
              lessons: [
                { lesson_id: L1, title: "Định nghĩa đạo hàm", section_title: "Đạo hàm", done_count: 9, completion_rate: 0.75 },
              ],
              quizzes: [
                { quiz_id: QUIZ_ID, lesson_id: L1, title: "Kiểm tra đạo hàm cơ bản", status: "published", attempts: 10, students: 8, avg_score: 71.25, pass_rate: 0.625 },
              ],
              tutor: { sessions: 20, questions: 57, refused_answers: 4 },
            },
          }),
      },
    });
    await page.goto("/teach/giai-tich-1/analytics");
    await expect(page.getByRole("heading", { name: "Thống kê khóa học" })).toBeVisible();
    await expect(page.getByText("9/12 · 75%")).toBeVisible();
    await expect(page.getByText("71.3%")).toBeVisible();
    await expect(page.getByText("63%")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });
});
