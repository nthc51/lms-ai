import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { mockApi, teacher } from "./mock-api";

const err = (code: string, message: string) => ({ error: { code, message, details: {}, request_id: "rq-e2e" } });

test.describe("xác nhận email", () => {
  test("đăng ký xong thì phải kiểm tra hộp thư, gửi lại được link", async ({ page }) => {
    let resendBody: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/register": (r) => r.fulfill({ status: 201, json: { ...teacher, id: "u-5", email: "moi@sv.vn", role: "student", teacher_status: null, email_verified: false } }),
        "POST /auth/resend-verification": (r) => {
          resendBody = r.request().postDataJSON();
          return r.fulfill({ status: 202, json: { status: "accepted" } });
        },
      },
    });
    await page.goto("/register");
    await page.getByLabel("Họ và tên").fill("Nguyễn Văn Mới");
    await page.getByLabel("Email").fill("Moi@SV.vn");
    await page.getByLabel("Mật khẩu").fill("password123");
    await page.getByRole("button", { name: "Tạo tài khoản" }).click();

    await expect(page.getByRole("heading", { name: "Kiểm tra hộp thư của bạn" })).toBeVisible();
    await expect(page.getByText("moi@sv.vn")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByRole("button", { name: "Gửi lại email xác nhận" }).click();
    await expect(page.getByText(/Đã gửi lại/)).toBeVisible();
    expect(resendBody).toEqual({ email: "moi@sv.vn" });
  });

  test("đăng nhập khi chưa xác nhận: báo rõ và cho gửi lại; gửi quá nhiều thì báo thời gian chờ", async ({ page }) => {
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/login": (r) => r.fulfill({ status: 403, json: err("EMAIL_NOT_VERIFIED", "Bạn cần xác nhận email trước khi đăng nhập") }),
        "POST /auth/resend-verification": (r) =>
          r.fulfill({ status: 429, headers: { "Retry-After": "1500" }, json: err("RATE_LIMITED", "Bạn đã yêu cầu gửi lại quá nhiều lần") }),
      },
    });
    await page.goto("/login");
    await page.getByLabel("Email").fill("an@sv.vn");
    await page.getByLabel("Mật khẩu").fill("password123");
    await page.getByRole("button", { name: "Đăng nhập" }).click();
    const alert = page.getByRole("alert").filter({ hasText: "Bạn cần xác nhận email" });
    await expect(alert).toContainText("an@sv.vn");
    await alert.getByRole("button", { name: "Gửi lại email xác nhận" }).click();
    await expect(page.getByText(/Thử lại sau khoảng 25 phút/)).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("bấm link trong email: xác nhận thành công", async ({ page }) => {
    let body: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/verify-email": (r) => {
          body = r.request().postDataJSON();
          return r.fulfill({ json: { ...teacher, teacher_status: "pending", email_verified: true } });
        },
      },
    });
    await page.goto("/verify-email?token=abc123xyz789");
    await expect(page.getByRole("heading", { name: "Email đã được xác nhận" })).toBeVisible();
    await expect(page.getByText(/đang chờ quản trị viên duyệt/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Đăng nhập" }).last()).toHaveAttribute("href", "/login");
    expect(body).toEqual({ token: "abc123xyz789" });
    await expectAccessible(page);
  });

  test("link hết hạn: nhập email để nhận link mới", async ({ page }) => {
    let resendBody: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/verify-email": (r) => r.fulfill({ status: 400, json: err("TOKEN_EXPIRED", "Link xác nhận đã hết hạn, hãy gửi lại email xác nhận") }),
        "POST /auth/resend-verification": (r) => {
          resendBody = r.request().postDataJSON();
          return r.fulfill({ status: 202, json: { status: "accepted" } });
        },
      },
    });
    await page.goto("/verify-email?token=het-han-roi-123");
    await expect(page.getByRole("heading", { name: "Link đã hết hạn" })).toBeVisible();
    await page.getByLabel("Email đã đăng ký").fill("an@sv.vn");
    await page.getByRole("button", { name: "Gửi link xác nhận mới" }).click();
    await expect(page.getByText(/link mới đã được gửi/)).toBeVisible();
    expect(resendBody).toEqual({ email: "an@sv.vn" });
    await expectAccessible(page);
  });
});

test("giảng viên bị từ chối gửi lại yêu cầu duyệt", async ({ page }) => {
  let status = "rejected";
  await mockApi(page, {
    user: { ...teacher, teacher_status: "rejected" },
    extra: {
      "GET /me": (r) => r.fulfill({ json: { ...teacher, teacher_status: status, review_note: status === "rejected" ? "Thiếu minh chứng" : null } }),
      "POST /me/teacher-request": (r) => {
        status = "pending";
        return r.fulfill({ json: { ...teacher, teacher_status: "pending", review_note: null } });
      },
    },
  });
  await page.goto("/");
  await expect(page.getByText(/Lý do: Thiếu minh chứng/)).toBeVisible();
  await page.getByRole("button", { name: "Gửi lại yêu cầu duyệt" }).click();
  await expect(page.getByText("Tài khoản giảng viên đang chờ duyệt")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gửi lại yêu cầu duyệt" })).toHaveCount(0);
});
