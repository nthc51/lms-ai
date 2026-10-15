import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, L2, mockApi } from "./mock-api";

test("trang chủ học viên: thẻ Học tiếp vào thẳng bài đang học, thanh dưới không còn mục Tài khoản", async ({ page, isMobile }) => {
  await page.addInitScript(
    ([courseId, lessonId]) => localStorage.setItem(`lms:last-lesson:${courseId}`, JSON.stringify(lessonId)),
    [COURSE_ID, L2],
  );
  await mockApi(page);
  await page.goto("/");
  const resume = page.getByRole("region", { name: "Giải tích 1" });
  await expect(resume.getByRole("link", { name: "Học tiếp" })).toHaveAttribute("href", `/learn/giai-tich-1/${L2}`);
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
