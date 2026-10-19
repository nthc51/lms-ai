import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, courseDetail, L1, mockApi, teacher } from "./mock-api";

const now = () => new Date(Date.now() - 5 * 60_000).toISOString();

const reply = {
  id: "c-2",
  parent_id: "c-1",
  body: "Em xem lại ví dụ ở trang 4 giáo trình nhé.",
  deleted: false,
  author_name: "Trần Thị Bình",
  author_role: "teacher",
  is_course_teacher: true,
  can_delete: false,
  created_at: now(),
  replies: [],
};
const thread = {
  id: "c-1",
  parent_id: null,
  body: "Tại sao h phải tiến về 0 mà không bằng 0 ạ?",
  deleted: false,
  author_name: "Nguyễn Văn An",
  author_role: "student",
  is_course_teacher: false,
  can_delete: true,
  created_at: now(),
  replies: [reply],
};

test.describe("thảo luận và thông báo", () => {
  test("học viên nhận thông báo có trả lời, bấm vào thì tới đúng phần thảo luận của bài và hỏi tiếp", async ({ page }) => {
    let unread = 1;
    let marked = "";
    let posted: unknown = null;
    const notif = {
      id: "n-1",
      kind: "comment_reply",
      title: "Trần Thị Bình đã trả lời bạn",
      body: reply.body,
      link: `/learn/giai-tich-1/${L1}#thao-luan`,
      read: false,
      created_at: now(),
    };
    await mockApi(page, {
      extra: {
        "GET /me/notifications/unread": (r) => r.fulfill({ json: { unread } }),
        "GET /me/notifications/stream": (r) =>
          r.fulfill({ status: 200, contentType: "text/event-stream", body: `event: unread\ndata: {"unread": ${unread}, "latest": null}\n\n` }),
        "GET /me/notifications": (r) =>
          r.fulfill({ json: { items: [{ ...notif, read: unread === 0 }], total: 1, page: 1, size: 10, unread } }),
        "POST /me/notifications/*/read": (r) => {
          marked = new URL(r.request().url()).pathname.split("/").at(-2) ?? "";
          unread = 0;
          return r.fulfill({ status: 204 });
        },
        "GET /lessons/*/comments": (r) => r.fulfill({ json: { items: [thread], total: 1, page: 1, size: 10 } }),
        "POST /lessons/*/comments": (r) => {
          posted = r.request().postDataJSON();
          return r.fulfill({ status: 201, json: { ...thread, id: "c-3", replies: [] } });
        },
      },
    });
    await page.goto("/");
    const bell = page.getByRole("button", { name: "Thông báo, 1 chưa đọc" });
    await expect(bell).toBeVisible();
    await bell.click();
    await expect(page.getByRole("heading", { name: "Thông báo" })).toBeVisible();
    await expectAccessible(page);
    await page.getByRole("link", { name: /Trần Thị Bình đã trả lời bạn/ }).click();

    await expect(page).toHaveURL(new RegExp(`/learn/giai-tich-1/${L1}#thao-luan$`));
    expect(marked).toBe("n-1");
    const section = page.getByRole("region", { name: /Thảo luận/ });
    await expect(section.getByText(reply.body)).toBeInViewport();
    await expect(section.getByText("Giảng viên", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Thông báo", exact: true })).toBeVisible();

    await section.getByRole("button", { name: "Trả lời" }).click();
    await section.getByLabel("Trả lời Nguyễn Văn An").fill("Em cảm ơn cô, em hiểu rồi ạ.");
    await section.getByRole("button", { name: "Gửi trả lời" }).click();
    await expect.poll(() => posted).toEqual({ body: "Em cảm ơn cô, em hiểu rồi ạ.", parent_id: "c-1" });
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("giảng viên xem phân tích lớp: câu hay sai, bài cần xem lại, học viên cần để ý", async ({ page }) => {
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: courseDetail({ is_owner: true }) }),
        [`GET /courses/${COURSE_ID}/analytics`]: (r) =>
          r.fulfill({
            json: {
              course_id: COURSE_ID,
              enrollments: 12,
              completed_enrollments: 3,
              lessons: [{ lesson_id: L1, title: "Định nghĩa đạo hàm", section_title: "Đạo hàm", done_count: 9, completion_rate: 0.75 }],
              quizzes: [],
              tutor: { sessions: 20, questions: 57, refused_answers: 4 },
            },
          }),
        "GET /courses/*/insights": (r) =>
          r.fulfill({
            json: {
              course_id: COURSE_ID,
              min_answers: 3,
              hard_questions: [
                {
                  question_id: "q-1",
                  stem: "Đạo hàm của x² tại x = 3 bằng bao nhiêu?",
                  lesson_id: L1,
                  lesson_title: "Định nghĩa đạo hàm",
                  answers: 10,
                  wrong: 7,
                  wrong_rate: 0.7,
                  correct_option: "B",
                  top_wrong: { id: "A", text: "3", count: 5 },
                  source_page: 4,
                },
              ],
              weak_lessons: [
                { lesson_id: L1, title: "Định nghĩa đạo hàm", section_title: "Đạo hàm", attempts: 10, avg_score: 42.5, tutor_questions: 31 },
              ],
              students_at_risk: [
                {
                  user_id: "u-9",
                  full_name: "Lê Minh Châu",
                  progress_pct: 15,
                  avg_score: 30,
                  last_active_at: new Date(Date.now() - 10 * 86_400_000).toISOString(),
                  reasons: ["Điểm quiz trung bình 30%", "Không học 10 ngày"],
                },
              ],
            },
          }),
      },
    });
    await page.goto("/teach/giai-tich-1/analytics");
    await expect(page.getByRole("heading", { name: "Câu hỏi học viên hay làm sai" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Đạo hàm của x²/ })).toHaveAttribute(
      "href",
      `/teach/giai-tich-1/lessons/${L1}/questions`,
    );
    await expect(page.getByText("70% sai")).toBeVisible();
    await expect(page.getByText("42.5%")).toBeVisible();
    await expect(page.getByText("Không học 10 ngày")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });
});
