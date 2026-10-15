import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { L1, mockApi, student } from "./mock-api";

test.describe("hồ sơ cá nhân và menu tài khoản", () => {
  test("mở Hồ sơ cá nhân từ menu ở trang bất kỳ, sửa họ tên và đổi mật khẩu", async ({ page }) => {
    let me = { ...student, email_verified: true };
    const bodies: Record<string, unknown> = {};
    await mockApi(page, {
      extra: {
        "GET /me": (r) => r.fulfill({ json: me }),
        "PATCH /me": (r) => {
          bodies.profile = r.request().postDataJSON();
          me = { ...me, full_name: (bodies.profile as { full_name: string }).full_name };
          return r.fulfill({ json: me });
        },
        "POST /me/password": (r) => {
          bodies.password = r.request().postDataJSON();
          return r.fulfill({ json: { access_token: "tok-2", token_type: "bearer" } });
        },
      },
    });
    await page.goto("/explore");
    await page.getByRole("button", { name: /Nguyễn Văn An/ }).click();
    await page.getByRole("menuitem", { name: "Hồ sơ cá nhân" }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole("heading", { name: "Hồ sơ cá nhân", level: 1 })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByLabel("Họ tên").fill("Nguyễn Văn Bình");
    await page.getByRole("button", { name: "Lưu họ tên" }).click();
    await expect(page.getByText("Đã lưu họ tên")).toBeVisible();
    expect(bodies.profile).toEqual({ full_name: "Nguyễn Văn Bình" });
    // menu ở thanh trên đọc tên mới
    await expect(page.getByRole("button", { name: /Nguyễn Văn Bình/ })).toBeVisible();

    await page.getByLabel("Mật khẩu hiện tại").fill("password123");
    await page.getByLabel("Mật khẩu mới", { exact: true }).fill("mat-khau-moi-1");
    await page.getByLabel("Nhập lại mật khẩu mới").fill("mat-khau-moi-1");
    await page.getByRole("button", { name: "Đổi mật khẩu" }).click();
    await expect(page.getByText(/Đã đổi mật khẩu/)).toBeVisible();
    expect(bodies.password).toEqual({ current_password: "password123", new_password: "mat-khau-moi-1" });
  });

  test("đang học bài vẫn mở được menu tài khoản và đăng xuất về trang chủ", async ({ page }) => {
    let loggedOut = false;
    await mockApi(page, {
      extra: {
        "POST /auth/logout": (r) => {
          loggedOut = true;
          return r.fulfill({ status: 204 });
        },
        "POST /auth/refresh": (r) =>
          loggedOut
            ? r.fulfill({ status: 401, json: { error: { code: "INVALID_TOKEN", message: "x", details: {} } } })
            : r.fulfill({ json: { access_token: "tok", token_type: "bearer" } }),
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await expect(page.getByRole("heading", { name: "Định nghĩa đạo hàm", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: /Nguyễn Văn An/ }).click();
    await expect(page.getByRole("menuitem", { name: "Hồ sơ cá nhân" })).toBeVisible();
    await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Hỏi bài, có số trang.", level: 1 })).toBeVisible();
    expect(loggedOut).toBe(true);
  });
});
