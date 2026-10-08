import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, L1, mockApi, note, studioOverview } from "./mock-api";

const ART = "a-1";
const FC = "a-2";
const cite = { n: 1, chunk_id: "k1", lesson_id: L1, page_no: 4, start_sec: null, lesson_title: "Định nghĩa đạo hàm", heading_path: "Chương 2", snippet: "Đạo hàm là giới hạn…" };
const artifact = (over: Record<string, unknown> = {}) => ({
  id: ART,
  course_id: COURSE_ID,
  lesson_id: L1,
  kind: "study_guide",
  status: "ready",
  content_md: "## Mục tiêu\n\nHiểu định nghĩa đạo hàm [1].",
  cards: null,
  citations: [cite],
  error_msg: null,
  stale: false,
  reviewed: false,
  created_at: "2026-10-01T00:00:00Z",
  known_cards: [],
  ...over,
});
const chunk = { id: "k1", source_id: "src-1", lesson_id: L1, lesson_title: "Định nghĩa đạo hàm", heading_path: "Chương 2", page_no: 4, start_sec: null, content: "Toàn văn: đạo hàm của f tại x0 là giới hạn của tỉ số gia số." };

/** Mở cột "Trợ lý học tập" (điện thoại: khung trượt) rồi chọn tab. */
async function openTab(page: import("@playwright/test").Page, name: string) {
  await page.getByRole("button", { name: "Hỏi AI" }).first().click();
  await page.getByRole("tab", { name }).click();
}

test.describe("AI Studio", () => {
  test("Studio: bấm Tạo → đang soạn → xong thì Mở xem báo cáo, xem trước nguồn [1]", async ({ page }) => {
    let calls = 0;
    let requested = false;
    await mockApi(page, {
      extra: {
        "GET /studio": (r) => {
          calls++;
          if (!requested) return r.fulfill({ json: studioOverview() });
          // lần poll đầu sau khi bấm: đang soạn; sau đó: xong
          const done = calls > 3;
          return r.fulfill({
            json: studioOverview({
              study_guide: done ? { status: "ready", artifact_id: ART, created_at: "2026-10-01T00:00:00Z" } : { status: "generating", job_id: "j-1" },
            }),
          });
        },
        "POST /studio/study_guide": (r) => {
          requested = true;
          return r.fulfill({ status: 202, json: { artifact_id: ART, status: "generating", job_id: "j-1" } });
        },
        [`GET /studio/artifacts/${ART}`]: (r) => r.fulfill({ json: artifact() }),
        "GET /chunks/k1": (r) => r.fulfill({ json: chunk }),
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await openTab(page, "Studio");
    await expectAccessible(page);
    await page.getByRole("button", { name: "Tạo Đề cương ôn tập" }).click();
    await expect(page.getByText(/AI đang soạn/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Mở Đề cương ôn tập" })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Mở Đề cương ôn tập" }).click();

    const dialog = page.getByRole("dialog", { name: "Đề cương ôn tập" });
    await expect(dialog.getByRole("heading", { name: "Mục tiêu" })).toBeVisible();
    await expectNoHorizontalScroll(page);
    await dialog.getByRole("button", { name: /Nguồn 1, trang 4/ }).click();
    // có đoạn trích sẵn trong citations → hiện ngay; đoạn tài liệu được tải để biết file PDF
    await expect(page.getByText("Đạo hàm là giới hạn…")).toBeVisible();
    await expect(page.getByRole("button", { name: "Mở PDF trang 4" })).toBeVisible();
  });

  test("Flashcard: lật thẻ, đánh dấu Nhớ rồi, lọc thẻ chưa nhớ", async ({ page }) => {
    const reviews: string[] = [];
    await mockApi(page, {
      extra: {
        "GET /studio": (r) => r.fulfill({ json: studioOverview({ flashcards: { status: "ready", artifact_id: FC, created_at: "2026-10-01T00:00:00Z" } }) }),
        [`GET /studio/artifacts/${FC}`]: (r) =>
          r.fulfill({
            json: artifact({
              id: FC,
              kind: "flashcards",
              content_md: "",
              cards: [
                { front: "Đạo hàm là gì?", back: "Giới hạn của tỉ số gia số", sources: [1] },
                { front: "Đạo hàm của hằng số?", back: "Bằng 0", sources: [] },
              ],
            }),
          }),
        "PUT /studio/artifacts/*/cards/*": (r, url) => {
          reviews.push(url.pathname.split("/").pop()!);
          return r.fulfill({ status: 204 });
        },
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await openTab(page, "Studio");
    await page.getByRole("button", { name: "Mở Flashcard" }).click();
    const dialog = page.getByRole("dialog", { name: "Flashcard" });
    await expect(dialog.getByText("Đạo hàm là gì?")).toBeVisible();
    await dialog.getByRole("button", { name: /bấm để lật xem đáp án/ }).click();
    await expect(dialog.getByText("Giới hạn của tỉ số gia số")).toBeVisible();
    await dialog.getByRole("button", { name: "Nhớ rồi" }).click();
    await expect.poll(() => reviews).toEqual(["0"]);
    await expect(dialog.getByRole("progressbar", { name: "Đã nhớ 1 trên 2 thẻ" })).toBeVisible();
    await expectAccessible(page);
  });

  test("Tài liệu: hướng dẫn tài liệu + câu hỏi gợi ý chuyển sang AI Tutor", async ({ page }) => {
    await mockApi(page, {
      extra: {
        "GET /lessons/*/documents": (r) =>
          r.fulfill({
            json: [
              {
                source_id: "src-1",
                title: "Giáo trình đạo hàm",
                page_count: 12,
                guide: { status: "ready", title: "Giáo trình đạo hàm", summary: "Tài liệu trình bày định nghĩa và quy tắc tính đạo hàm.", topics: ["Định nghĩa", "Quy tắc"], questions: ["Đạo hàm một phía là gì?"] },
              },
            ],
          }),
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await openTab(page, "Tài liệu");
    await expect(page.getByText("Tài liệu trình bày định nghĩa")).toBeVisible();
    await expectAccessible(page);
    await page.getByRole("button", { name: "Đạo hàm một phía là gì?" }).click();
    await expect(page.getByRole("tab", { name: "AI Tutor" })).toHaveAttribute("aria-selected", "true");
  });

  test("AI Tutor: gợi ý hỏi tiếp + lưu câu trả lời vào ghi chú", async ({ page }) => {
    let saved = false;
    await mockApi(page, {
      extra: {
        "POST /tutor/messages/*/followups": (r) => r.fulfill({ json: { questions: ["Đạo hàm một phía là gì?", "Khi nào hàm không có đạo hàm?"] } }),
        "POST /notes/from-message": (r) => {
          saved = true;
          return r.fulfill({ status: 201, json: note() });
        },
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await page.getByRole("button", { name: "Hỏi AI" }).first().click();
    const input = page.getByLabel("Câu hỏi cho AI Tutor");
    await input.fill("Đạo hàm là gì?");
    await input.press("Enter");
    await expect(page.getByText(/tiến về 0/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Khi nào hàm không có đạo hàm?" })).toBeVisible();
    await page.getByRole("button", { name: "Lưu vào ghi chú" }).click();
    await expect.poll(() => saved).toBe(true);
    await expect(page.getByText("Đã lưu vào ghi chú")).toBeVisible();
  });

  test("Sổ ghi chú: chọn 2 ghi chú → tạo đề cương; sửa ghi chú", async ({ page }) => {
    let synthBody: unknown = null;
    let patched: unknown = null;
    await mockApi(page, {
      extra: {
        "GET /notes": (r) => r.fulfill({ json: { items: [note(), note({ id: "n-2", title: "Quy tắc tính", content_md: "Tổng, hiệu, tích, thương.", citations: [] })], total: 2, page: 1, size: 20 } }),
        "POST /notes/synthesize": async (r) => {
          synthBody = r.request().postDataJSON();
          return r.fulfill({ status: 202, json: { note: note({ id: "n-3", status: "generating" }), job_id: "j-9" } });
        },
        "PATCH /notes/n-2": async (r) => {
          patched = r.request().postDataJSON();
          return r.fulfill({ json: note({ id: "n-2", title: "Quy tắc tính đạo hàm" }) });
        },
      },
    });
    await page.goto("/notes");
    await expect(page.getByRole("heading", { name: "Ghi chú của tôi", level: 1 })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByRole("checkbox", { name: "Chọn ghi chú Đạo hàm là gì?" }).check();
    await page.getByRole("checkbox", { name: "Chọn ghi chú Quy tắc tính" }).check();
    await page.getByRole("button", { name: "Tạo đề cương từ 2 ghi chú" }).click();
    await expect.poll(() => synthBody).toEqual({ note_ids: ["n-1", "n-2"] });

    await page.getByRole("button", { name: "Sửa Quy tắc tính" }).click();
    const dialog = page.getByRole("dialog", { name: "Sửa ghi chú" });
    await dialog.getByLabel("Tiêu đề").fill("Quy tắc tính đạo hàm");
    await dialog.getByRole("button", { name: "Lưu" }).click();
    await expect.poll(() => (patched as { title?: string } | null)?.title).toBe("Quy tắc tính đạo hàm");
  });

  test("menu tài khoản có lối vào Sổ ghi chú", async ({ page, isMobile }) => {
    test.skip(isMobile, "menu tài khoản kiểm ở desktop");
    await mockApi(page);
    await page.goto("/");
    await page.getByRole("button", { name: /Nguyễn Văn An/ }).click();
    await page.getByRole("menuitem", { name: "Ghi chú của tôi" }).click();
    await expect(page).toHaveURL(/\/notes$/);
  });
});
