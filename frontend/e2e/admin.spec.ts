import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { admin, adminCourse, page as pageOf, pendingTeacher, stats, studentRow } from "./admin-data";
import { courseDetail, mockApi, teacher } from "./mock-api";

test.describe("quản trị viên", () => {
  test("đăng nhập xong vào thẳng Tổng quan: số liệu, giảng viên chờ duyệt, nhật ký", async ({ page }) => {
    let loggedIn = false;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/login": (r) => {
          loggedIn = true;
          return r.fulfill({ json: { access_token: "tok", token_type: "bearer" } });
        },
        "GET /me": (r) => (loggedIn ? r.fulfill({ json: admin }) : r.fulfill({ status: 401, json: { error: { code: "NOT_AUTHENTICATED", message: "x" } } })),
        "GET /admin/stats": (r) => r.fulfill({ json: stats() }),
        "GET /admin/users": (r) => r.fulfill({ json: pageOf([pendingTeacher]) }),
        "GET /admin/actions": (r) =>
          r.fulfill({
            json: pageOf([
              { id: "a1", admin_name: "Quản trị viên", action: "hide_course", target_type: "course", target_id: "c", target_label: "Khóa X", note: "Vi phạm bản quyền", created_at: "2026-10-06T03:00:00Z" },
            ]),
          }),
      },
    });
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Mật khẩu").fill("Admin12345");
    await page.getByRole("button", { name: "Đăng nhập" }).click();

    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole("heading", { name: "Tổng quan hệ thống" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Giảng viên chờ duyệt\s*1/ })).toHaveAttribute("href", "/admin/users?tab=pending");
    await expect(page.getByRole("cell", { name: /cuong@gv\.vn/ })).toBeVisible();
    await expect(page.getByText("Lý do: Vi phạm bản quyền")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("duyệt và từ chối giảng viên (từ chối bắt buộc ghi lý do)", async ({ page }) => {
    const calls: { path: string; body: unknown }[] = [];
    let pending = [pendingTeacher, { ...pendingTeacher, id: "u-4", email: "dung@gv.vn", full_name: "Lê Thị Dung" }];
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/users": (r) => r.fulfill({ json: pageOf(pending) }),
        "POST /admin/teachers/*/approve": (r, url) => {
          calls.push({ path: url.pathname, body: null });
          pending = pending.filter((u) => !url.pathname.includes(u.id));
          return r.fulfill({ json: { ...pendingTeacher, teacher_status: "approved" } });
        },
        "POST /admin/teachers/*/reject": (r, url) => {
          calls.push({ path: url.pathname, body: r.request().postDataJSON() });
          pending = pending.filter((u) => !url.pathname.includes(u.id));
          return r.fulfill({ json: { ...pendingTeacher, teacher_status: "rejected" } });
        },
      },
    });
    await page.goto("/admin/users?tab=pending");
    await expect(page.getByRole("button", { name: "Chờ duyệt" })).toHaveAttribute("aria-pressed", "true");
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByRole("button", { name: "Duyệt Phạm Văn Cường" }).click();
    await expect(page.getByRole("cell", { name: /cuong@gv\.vn/ })).toBeHidden();

    await page.getByRole("button", { name: "Từ chối Lê Thị Dung" }).click();
    const dialog = page.getByRole("dialog", { name: "Từ chối Lê Thị Dung?" });
    await dialog.getByRole("button", { name: "Từ chối" }).click();
    await expect(dialog.getByText("Cần nhập lý do")).toBeVisible();
    await dialog.getByLabel("Lý do").fill("Chưa có minh chứng chuyên môn");
    await dialog.getByRole("button", { name: "Từ chối" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText("Không có giảng viên nào đang chờ duyệt.")).toBeVisible();
    expect(calls).toEqual([
      { path: "/api/v1/admin/teachers/u-3/approve", body: null },
      { path: "/api/v1/admin/teachers/u-4/reject", body: { reason: "Chưa có minh chứng chuyên môn" } },
    ]);
  });

  test("tab Học viên lọc đúng và khóa tài khoản", async ({ page }) => {
    const queries: string[] = [];
    let locked = false;
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/users": (r, url) => {
          queries.push(url.search);
          return r.fulfill({ json: pageOf([{ ...studentRow, locked_at: locked ? "2026-10-06T03:00:00Z" : null }]) });
        },
        "POST /admin/users/*/lock": (r) => {
          locked = true;
          return r.fulfill({ json: { ...studentRow, locked_at: "2026-10-06T03:00:00Z" } });
        },
      },
    });
    await page.goto("/admin/users");
    await page.getByRole("button", { name: "Học viên" }).click();
    await expect(page).toHaveURL(/tab=student/);
    await expect.poll(() => queries.at(-1)).toContain("role=student");
    await page.getByRole("button", { name: "Khóa tài khoản Nguyễn Văn An" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Khóa tài khoản" }).click(); // lý do không bắt buộc
    await expect(page.getByRole("cell", { name: "Đã khóa", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Mở khóa Nguyễn Văn An" })).toBeVisible();
  });

  test("ẩn khóa học vi phạm kèm lý do", async ({ page }) => {
    let hidden: Record<string, unknown> | null = null;
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/courses": (r) => r.fulfill({ json: pageOf([adminCourse(hidden ? { status: "archived", hidden_at: "2026-10-06T03:00:00Z", hidden_reason: "Sao chép giáo trình" } : {})]) }),
        "POST /admin/courses/*/hide": (r) => {
          hidden = r.request().postDataJSON();
          return r.fulfill({ json: adminCourse({ status: "archived" }) });
        },
      },
    });
    await page.goto("/admin/courses");
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByRole("button", { name: "Ẩn Giải tích 1" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/35 học viên/)).toBeVisible();
    await dialog.getByLabel("Lý do").fill("Sao chép giáo trình");
    await dialog.getByRole("button", { name: "Ẩn khóa học" }).click();
    await expect(page.getByText("Lý do ẩn: Sao chép giáo trình")).toBeVisible();
    await expect(page.getByRole("button", { name: "Hiện lại Giải tích 1" })).toBeVisible();
    expect(hidden).toEqual({ reason: "Sao chép giáo trình" });
  });
});

test.describe("phân quyền và thông báo cho giảng viên", () => {
  test("giảng viên mở /admin thấy thông báo không có quyền", async ({ page }) => {
    await mockApi(page, { user: teacher });
    await page.goto("/admin");
    await expect(page.getByText("Trang này chỉ dành cho quản trị viên.")).toBeVisible();
  });

  test("giảng viên bị từ chối thấy lý do ở trang chủ", async ({ page }) => {
    const rejected = { ...teacher, teacher_status: "rejected", review_note: "Chưa có minh chứng chuyên môn" };
    await mockApi(page, { user: rejected });
    await page.goto("/");
    await expect(page.getByText("Yêu cầu giảng dạy chưa được chấp nhận")).toBeVisible();
    await expect(page.getByText(/Lý do: Chưa có minh chứng chuyên môn/)).toBeVisible();
    await expectAccessible(page);
  });

  test("khóa bị ẩn: trình soạn hiện lý do và không còn nút Xuất bản", async ({ page }) => {
    const hiddenCourse = courseDetail({ status: "archived", is_owner: true, hidden_reason: "Sao chép giáo trình" });
    await mockApi(page, { user: teacher, extra: { "GET /courses/giai-tich-1": (r) => r.fulfill({ json: hiddenCourse }) } });
    await page.goto("/teach/giai-tich-1");
    await expect(page.getByRole("alert").filter({ hasText: "Quản trị viên đã ẩn khóa học này" })).toContainText("Sao chép giáo trình");
    await expect(page.getByText("Đã bị ẩn")).toBeVisible();
    await expect(page.getByRole("button", { name: "Xuất bản" })).toHaveCount(0);
    await expectAccessible(page);
  });
});

test.describe("quản trị viên: phản hồi AI và xuất CSV", () => {
  test("trang câu trả lời AI bị chê", async ({ page }) => {
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/tutor-feedback": (r) =>
          r.fulfill({
            json: pageOf([
              { message_id: "m1", question: "Đạo hàm của x² là gì?", answer: "Là x [1].", refused: false, created_at: "2026-10-06T03:00:00Z", course_id: "c", course_title: "Giải tích 1", course_slug: "giai-tich-1", lesson_id: "l", lesson_title: "Định nghĩa đạo hàm", student_name: "Nguyễn Văn An" },
            ]),
          }),
      },
    });
    await page.goto("/admin/feedback");
    await expect(page.getByText("Đạo hàm của x² là gì?")).toBeVisible();
    await expect(page.getByText("· Nguyễn Văn An")).toBeVisible();
    await page.getByText("Câu trả lời của AI").click();
    await expect(page.getByText("Là x [1].")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("xuất CSV theo tab đang xem", async ({ page }) => {
    let query = "";
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/users": (r) => r.fulfill({ json: pageOf([studentRow]) }),
        "GET /admin/users/export": (r, url) => {
          query = url.search;
          return r.fulfill({ status: 200, contentType: "text/csv; charset=utf-8", body: "﻿Họ tên,Email\nNguyễn Văn An,an@sv.vn\n" });
        },
      },
    });
    await page.goto("/admin/users?tab=student");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Xuất CSV" }).click();
    expect((await download).suggestedFilename()).toMatch(/^nguoi-dung-\d{4}-\d{2}-\d{2}\.csv$/);
    expect(query).toContain("role=student");
  });
});
