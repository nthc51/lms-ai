import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { mockApi, student } from "./mock-api";

const err = (code: string, message: string) => ({ error: { code, message, details: {}, request_id: "rq-e2e" } });

test.describe("quên mật khẩu", () => {
  test("từ trang đăng nhập xin link đặt lại; gửi quá nhiều lần thì báo thời gian chờ", async ({ page }) => {
    const bodies: unknown[] = [];
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/forgot-password": (r) => {
          bodies.push(r.request().postDataJSON());
          return bodies.length === 1
            ? r.fulfill({ status: 202, json: { status: "accepted" } })
            : r.fulfill({ status: 429, headers: { "Retry-After": "600" }, json: err("RATE_LIMITED", "Chậm lại") });
        },
      },
    });
    await page.goto("/login");
    await page.getByRole("link", { name: "Quên mật khẩu?" }).click();
    await expect(page.getByRole("heading", { name: "Quên mật khẩu" })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByLabel("Email").fill("An@SV.vn");
    await page.getByRole("button", { name: "Gửi link đặt lại mật khẩu" }).click();
    await expect(page.getByRole("heading", { name: "Kiểm tra hộp thư" })).toBeFocused();
    await expect(page.getByText(/Nếu an@sv\.vn đã đăng ký/)).toBeVisible();
    expect(bodies[0]).toEqual({ email: "an@sv.vn" });

    await page.getByRole("button", { name: "Gửi lại hoặc dùng email khác" }).click();
    await page.getByLabel("Email").fill("an@sv.vn");
    await page.getByRole("button", { name: "Gửi link đặt lại mật khẩu" }).click();
    await expect(page.getByText(/Thử lại sau khoảng 10 phút/)).toBeVisible();
  });

  test("đặt mật khẩu mới: kiểm khớp hai ô, thành công thì mời đăng nhập lại", async ({ page }) => {
    let body: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/reset-password": (r) => {
          body = r.request().postDataJSON();
          return r.fulfill({ json: { ...student, email_verified: true } });
        },
      },
    });
    await page.goto("/reset-password?token=tok-123456789");
    await expect(page.getByRole("heading", { name: "Đặt mật khẩu mới" })).toBeVisible();
    await expectAccessible(page);
    await page.getByLabel("Mật khẩu mới", { exact: true }).fill("matkhau-moi-1");
    await page.getByLabel("Nhập lại mật khẩu mới").fill("matkhau-khac");
    await page.getByRole("button", { name: "Đặt mật khẩu mới" }).click();
    await expect(page.getByText("Hai mật khẩu chưa khớp")).toBeVisible();
    expect(body).toBeNull();

    await page.getByLabel("Nhập lại mật khẩu mới").fill("matkhau-moi-1");
    await page.getByRole("button", { name: "Đặt mật khẩu mới" }).click();
    await expect(page.getByRole("heading", { name: "Đã đặt mật khẩu mới" })).toBeFocused();
    expect(body).toEqual({ token: "tok-123456789", password: "matkhau-moi-1" });
    await page.getByRole("link", { name: "Đăng nhập" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("link đã dùng hoặc hết hạn: báo rõ và cho xin link mới", async ({ page }) => {
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/reset-password": (r) =>
          r.fulfill({ status: 400, json: err("TOKEN_EXPIRED", "Link đặt lại mật khẩu đã hết hạn, hãy yêu cầu link mới") }),
      },
    });
    await page.goto("/reset-password?token=tok-cu-123456");
    await page.getByLabel("Mật khẩu mới", { exact: true }).fill("matkhau-moi-1");
    await page.getByLabel("Nhập lại mật khẩu mới").fill("matkhau-moi-1");
    await page.getByRole("button", { name: "Đặt mật khẩu mới" }).click();
    await expect(page.getByRole("heading", { name: "Link không dùng được" })).toBeFocused();
    await expect(page.getByText(/đã hết hạn/)).toBeVisible();
    await page.getByRole("link", { name: "Gửi link mới" }).click();
    await expect(page.getByRole("heading", { name: "Quên mật khẩu" })).toBeVisible();
  });
});
