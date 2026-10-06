import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { courseDetail, L1, L2, mockApi, SECTION_ID, teacher } from "./mock-api";

const draft = courseDetail({ status: "draft", is_owner: true });

test.describe("giảng viên", () => {
  test("trình soạn: sắp xếp bằng nút ↑↓ gửi đúng thứ tự, xuất bản cần xác nhận", async ({ page }) => {
    let reorderBody: unknown = null;
    let published = false;
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: published ? { ...draft, status: "published" } : draft }),
        "PATCH /courses/*/reorder": (r) => {
          reorderBody = r.request().postDataJSON();
          return r.fulfill({ status: 204 });
        },
        "POST /courses/*/publish": (r) => {
          published = true;
          return r.fulfill({ json: { ...draft, status: "published" } });
        },
      },
    });
    await page.goto("/teach/giai-tich-1");
    await expect(page.getByText("Nháp")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByRole("button", { name: "Đưa bài Quy tắc tính đạo hàm lên" }).click();
    await expect.poll(() => reorderBody).toEqual({ sections: [{ id: SECTION_ID, lesson_ids: [L2, L1] }] });

    await page.getByRole("button", { name: "Xuất bản" }).click();
    const dialog = page.getByRole("alertdialog", { name: "Xuất bản khóa học?" });
    await expect(dialog.getByRole("button", { name: "Hủy" })).toBeFocused(); // Hủy được focus sẵn
    await dialog.getByRole("button", { name: "Xuất bản" }).click();
    await expect(page.getByText("Đã xuất bản")).toBeVisible();
  });

  test("xóa khóa học phải gõ lại đúng tên", async ({ page }) => {
    await mockApi(page, { user: teacher, extra: { "GET /courses/giai-tich-1": (r) => r.fulfill({ json: draft }) } });
    await page.goto("/teach/giai-tich-1");
    await page.getByRole("button", { name: "Xóa khóa học" }).click();
    const dialog = page.getByRole("alertdialog");
    const confirm = dialog.getByRole("button", { name: "Xóa vĩnh viễn" });
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel(/Gõ/).fill("Giải tích 1");
    await expect(confirm).toBeEnabled();
  });

  test("soạn bài: tự lưu nội dung và hiện 'Đã lưu lúc'", async ({ page }) => {
    let saved: Record<string, unknown> | null = null;
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: draft }),
        "GET /lessons/*/sources": (r) => r.fulfill({ json: [] }),
        "PATCH /lessons/*": (r) => {
          saved = r.request().postDataJSON();
          return r.fulfill({ json: { id: L1, section_id: SECTION_ID, title: "x", position: 0, content_md: "", duration_sec: null, video_asset_id: null } });
        },
      },
    });
    await page.goto(`/teach/giai-tich-1/lessons/${L1}`);
    await page.getByLabel("Nội dung bài (markdown)").fill("# Mới\n\nNội dung mới");
    await expect(page.getByText(/Đã lưu lúc/)).toBeVisible();
    expect(saved).toMatchObject({ content_md: "# Mới\n\nNội dung mới" });
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });
});
