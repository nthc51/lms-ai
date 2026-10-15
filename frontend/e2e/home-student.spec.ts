import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, L2, mockApi } from "./mock-api";

test("trang chủ học viên: khối Học tiếp vào thẳng bài đang học, quiz chưa làm, thanh dưới không còn mục Tài khoản", async ({ page, isMobile }) => {
  await page.addInitScript(
    ([courseId, lessonId]) => localStorage.setItem(`lms:last-lesson:${courseId}`, JSON.stringify(lessonId)),
    [COURSE_ID, L2],
  );
  await mockApi(page, {
    extra: {
      "GET /me/pending-quizzes": (r) =>
        r.fulfill({
          json: [
            {
              quiz_id: "q-1",
              title: "Kiểm tra đạo hàm",
              lesson_id: L2,
              lesson_title: "Quy tắc tính đạo hàm",
              course_title: "Giải tích 1",
              course_slug: "giai-tich-1",
              question_count: 10,
              time_limit_sec: 900,
              in_progress: false,
            },
          ],
        }),
    },
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Chào An.", level: 1 })).toBeVisible();
  const resume = page.getByRole("region", { name: "Giải tích 1" });
  await expect(resume.getByRole("link", { name: "Học tiếp" })).toHaveAttribute("href", `/learn/giai-tich-1/${L2}`);
  await expect(resume.getByText("Quy tắc tính đạo hàm")).toBeVisible();
  await expect(page.getByRole("link", { name: /Kiểm tra đạo hàm · Giải tích 1/ })).toHaveAttribute(
    "href",
    `/learn/giai-tich-1/${L2}/quiz/q-1`,
  );
  // chỉ 1 khóa nên không có "Xem tất cả"
  await expect(page.getByRole("link", { name: /Xem tất cả/ })).toHaveCount(0);
  if (isMobile) {
    const bottom = page.getByRole("navigation", { name: "Điều hướng chính" }).last();
    await expect(bottom.getByRole("link")).toHaveCount(3);
    await expect(bottom.getByRole("link", { name: "Tài khoản" })).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: /Nguyễn Văn An/ })).toBeVisible();
  await expectAccessible(page);
  await expectNoHorizontalScroll(page);
});
