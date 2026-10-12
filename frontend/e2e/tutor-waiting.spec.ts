import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, L1, mockApi } from "./mock-api";

const msg = (id: string, role: "user" | "assistant", content: string, waiting = false) => ({
  id,
  role,
  content,
  citations: [],
  refused: false,
  truncated: false,
  feedback: null,
  waiting_for_docs: waiting,
  created_at: "2026-10-12T00:00:00Z",
});

test("tài liệu đang xử lý: vẫn gửi được câu hỏi, AI trả lời khi xử lý xong", async ({ page }) => {
  let answered = false;
  await mockApi(page, {
    extra: {
      "GET /tutor/availability": (r) =>
        r.fulfill({
          json: answered
            ? { available: true, ready_chunks: 3, message: null, state: "ready", processing_docs: 0, can_queue: false }
            : {
                available: false,
                ready_chunks: 0,
                message: "Tài liệu đang được xử lý (1 tài liệu). Bạn vẫn có thể đặt câu hỏi: AI sẽ trả lời ngay khi xử lý xong.",
                state: "processing",
                processing_docs: 1,
                can_queue: true,
              },
        }),
      "POST /tutor/sessions/s-1/questions": (r) => r.fulfill({ status: 202, json: msg("q-1", "user", "Đạo hàm là gì?", true) }),
      "GET /tutor/sessions/s-1/messages": (r) =>
        r.fulfill({
          json: {
            items: answered
              ? [msg("q-1", "user", "Đạo hàm là gì?"), msg("a-1", "assistant", "Đạo hàm là giới hạn của tỉ số gia số.")]
              : [msg("q-1", "user", "Đạo hàm là gì?", true)],
            total: answered ? 2 : 1,
            page: 1,
            size: 100,
          },
        }),
      "POST /tutor/sessions": (r) =>
        r.fulfill({ status: 201, json: { id: "s-1", course_id: COURSE_ID, lesson_id: L1, created_at: "2026-10-12T00:00:00Z" } }),
    },
  });
  await page.goto(`/learn/giai-tich-1/${L1}`);
  await page.getByRole("button", { name: "Hỏi AI" }).first().click();
  await expect(page.getByText(/AI sẽ trả lời ngay khi xử lý xong/)).toBeVisible();
  const input = page.getByLabel("Câu hỏi cho AI Tutor");
  await expect(input).toBeEnabled();
  await input.fill("Đạo hàm là gì?");
  await input.press("Enter");
  await expect(page.getByText("Đang chờ tài liệu xử lý xong, AI sẽ trả lời ngay sau đó")).toBeVisible();
  await expectAccessible(page);
  await expectNoHorizontalScroll(page);

  answered = true;
  await expect(page.getByText("Đạo hàm là giới hạn của tỉ số gia số.")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("AI đã trả lời câu hỏi bạn gửi lúc tài liệu đang xử lý")).toBeVisible();
  await expect(page.getByText("Đang chờ tài liệu xử lý xong", { exact: false })).toBeHidden();
});
