import { expect, test } from "@playwright/test";
import { admin, page as pageOf, pendingTeacher } from "./admin-data";
import { mockApi, student } from "./mock-api";

test("mở link xác nhận khi trình duyệt đang có phiên đăng nhập: chỉ gửi xác nhận một lần", async ({ page }) => {
  let calls = 0;
  await mockApi(page, {
    user: student, // khôi phục phiên làm đổi người dùng → resetQueries; truy vấn xác nhận không được chạy lại
    extra: {
      "POST /auth/verify-email": (r) => {
        calls += 1;
        return calls === 1
          ? r.fulfill({ json: { ...student, email_verified: true } })
          : r.fulfill({ status: 400, json: { error: { code: "INVALID_TOKEN", message: "x", details: {}, request_id: null } } });
      },
    },
  });
  await page.goto("/verify-email?token=abc123xyz789");
  await expect(page.getByRole("heading", { name: "Email đã được xác nhận" })).toBeVisible();
  await page.waitForTimeout(800);
  await expect(page.getByRole("heading", { name: "Email đã được xác nhận" })).toBeVisible();
  expect(calls).toBe(1);
});

test("duyệt người cuối cùng ở trang 2: có nút về trang đầu, bấm Duyệt hai lần chỉ gửi một request", async ({ page }) => {
  let approves = 0;
  let remaining = 21;
  const rows = (p: number) =>
    Array.from({ length: Math.max(0, Math.min(20, remaining - (p - 1) * 20)) }, (_, i) => ({
      ...pendingTeacher,
      id: `u-${p}-${i}`,
      email: `gv${p}${i}@gv.vn`,
      full_name: `Giảng viên ${p}-${i}`,
    }));
  await mockApi(page, {
    user: admin,
    extra: {
      "GET /admin/users": (r, url) => {
        const p = Number(url.searchParams.get("page") ?? 1);
        return r.fulfill({ json: { items: rows(p), total: remaining, page: p, size: 20 } });
      },
      "POST /admin/teachers/*/approve": async (r) => {
        approves += 1;
        await new Promise((res) => setTimeout(res, 300)); // đủ lâu để cú bấm thứ hai rơi vào lúc đang xử lý
        remaining -= 1;
        return r.fulfill({ json: { ...pendingTeacher, teacher_status: "approved" } });
      },
    },
  });
  await page.goto("/admin/users?tab=pending");
  await page.getByRole("button", { name: "Trang sau" }).click();
  const approve = page.getByRole("button", { name: "Duyệt Giảng viên 2-0" });
  await approve.dblclick();
  await expect(page.getByText("Trang này không còn ai.")).toBeVisible();
  expect(approves).toBe(1);
  await page.getByRole("button", { name: "Về trang đầu" }).click();
  await expect(page.getByRole("button", { name: "Duyệt Giảng viên 1-0" })).toBeVisible();
});

test("admin vào trang chủ thì được chuyển sang khu quản trị", async ({ page }) => {
  await mockApi(page, {
    user: admin,
    extra: {
      "GET /admin/stats": (r) => r.fulfill({ status: 500, json: { error: { code: "X", message: "x", details: {}, request_id: null } } }),
      "GET /admin/users": (r) => r.fulfill({ json: pageOf([]) }),
      "GET /admin/actions": (r) => r.fulfill({ json: pageOf([]) }),
    },
  });
  await page.goto("/");
  await expect(page).toHaveURL(/\/admin$/);
});
