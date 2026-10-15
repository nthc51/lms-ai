import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { mockApi } from "./mock-api";

test.describe("trang chủ cho khách", () => {
  test("giới thiệu toàn màn hình, thử 4 câu hỏi mẫu, câu ngoài tài liệu thì AI từ chối", async ({ page }) => {
    await mockApi(page, { user: null });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Hỏi bài, có số trang.", level: 1 })).toBeVisible();
    // không có khung app (thanh điều hướng chính) ở trang giới thiệu
    await expect(page.getByRole("navigation", { name: "Điều hướng chính" })).toHaveCount(0);
    await expect(page.getByText("Mở PDF trang 49")).toBeVisible();

    await page.getByRole("button", { name: "Giá vé tàu" }).click();
    await expect(page.getByRole("button", { name: "Giá vé tàu" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(/không nói đến giá vé tàu/)).toBeVisible();
    await expect(page.getByText(/Mở PDF trang/)).toHaveCount(0);

    await page.getByRole("button", { name: "Dung lượng kênh" }).click();
    await expect(page.getByText("Mở PDF trang 31")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("nút Tạo tài khoản ở cuối trang dẫn tới đăng ký", async ({ page }) => {
    await mockApi(page, { user: null });
    await page.goto("/");
    await page.getByRole("link", { name: "Tạo tài khoản" }).last().click();
    await expect(page).toHaveURL(/\/register$/);
  });
});
