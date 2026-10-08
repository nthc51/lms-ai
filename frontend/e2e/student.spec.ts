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
    if (isMobile) await expect(page.getByRole("dialog", { name: "Trợ lý học tập" })).toBeHidden();

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
