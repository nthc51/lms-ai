import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { L1, mockApi } from "./mock-api";
import { ATTEMPT_ID, attempt, QUIZ_ID, quiz, result } from "./quiz-data";

test.describe("học viên làm quiz", () => {
  test("mở quiz từ bài học → chọn đáp án (tự lưu) → nộp có xác nhận → xem kết quả và giải thích", async ({ page }) => {
    const saved: Record<string, string> = {};
    let submitted: { final_answers: { question_id: string; selected_option_id: string }[] } | null = null;
    let used = 0;
    await mockApi(page, {
      extra: {
        "GET /quizzes": (r) => r.fulfill({ json: { items: [quiz({ attempts_used: used })], total: 1, page: 1, size: 50 } }),
        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz({ attempts_used: used }) }),
        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) => r.fulfill({ status: 201, json: attempt() }),
        [`PUT /attempts/${ATTEMPT_ID}/answers/*`]: async (r, url) => {
          const qid = url.pathname.split("/").pop()!;
          saved[qid] = r.request().postDataJSON().selected_option_id;
          await r.fulfill({ json: { question_id: qid, selected_option_id: saved[qid], answered_at: "2026-10-06T00:01:00Z" } });
        },
        [`POST /attempts/${ATTEMPT_ID}/submit`]: (r) => {
          submitted = r.request().postDataJSON();
          used = 1;
          const answers = Object.fromEntries(submitted!.final_answers.map((a) => [a.question_id, a.selected_option_id]));
          return r.fulfill({ json: result(answers) });
        },
      },
    });

    await page.goto(`/learn/giai-tich-1/${L1}`);
    await expect(page.getByRole("heading", { name: "Kiểm tra nhanh" })).toBeVisible();
    await page.getByRole("link", { name: "Làm bài" }).click();
    await expect(page).toHaveURL(new RegExp(`/quiz/${QUIZ_ID}$`));

    // Câu 1: chọn A (đúng) → thấy "Đã lưu"
    await expect(page.getByText("Câu 1/3")).toBeVisible();
    await page.getByRole("radio", { name: "0" }).check({ force: true });
    await expect(page.getByText("Đã lưu")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    // Câu 2: chọn A (sai), bỏ trống câu 3 → nộp → hộp xác nhận báo còn 1 câu
    await page.getByRole("button", { name: "Câu sau" }).click();
    await page.getByRole("radio", { name: "x", exact: true }).check({ force: true });
    await expect(page.getByText("Đã lưu")).toBeVisible();
    await page.getByRole("button", { name: "Câu sau" }).click();
    await page.getByRole("button", { name: "Nộp bài" }).first().click();
    const dialog = page.getByRole("alertdialog", { name: "Nộp bài?" });
    await expect(dialog).toContainText("Còn 1 câu chưa trả lời");
    await expect(dialog.getByRole("button", { name: "Hủy" })).toBeFocused();
    await dialog.getByRole("button", { name: "Nộp bài" }).click();

    // Kết quả
    await expect(page).toHaveURL(new RegExp(`/result/${ATTEMPT_ID}$`));
    expect(saved).toEqual({ "q-1": "A", "q-2": "A" });
    expect(submitted!.final_answers).toEqual([
      { question_id: "q-1", selected_option_id: "A" },
      { question_id: "q-2", selected_option_id: "A" },
    ]);
    await expect(page.getByText("33.3%")).toBeVisible();
    await expect(page.getByText("Chưa đạt")).toBeVisible();
    await expect(page.getByText("Câu 2 · Sai")).toBeVisible();
    await expect(page.getByText('Giải thích cho câu "Đạo hàm của x² là gì?"')).toBeVisible(); // câu sai mở sẵn giải thích
    await expect(page.getByRole("link", { name: /Làm lại \(1 lượt còn lại\)/ })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    // Quay lại bài học: thấy điểm gần nhất
    await page.getByRole("link", { name: "Về bài học" }).first().click();
    await expect(page.getByRole("link", { name: "Điểm gần nhất 33.3%" })).toBeVisible();
  });

  test("mở lại bài làm dở thì giữ đáp án đã lưu; hết lượt thì báo rõ", async ({ page }) => {
    await mockApi(page, {
      extra: {
        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz() }),
        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) => r.fulfill({ status: 200, json: attempt({ "q-1": "C" }) }),
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}/quiz/${QUIZ_ID}`);
    await expect(page.getByRole("radio", { name: "Chính hằng số đó" })).toBeChecked();
    await expect(page.getByText("Đã trả lời 1/3")).toBeVisible();

    await mockApi(page, {
      extra: {
        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz({ attempts_used: 2 }) }),
        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) =>
          r.fulfill({
            status: 409,
            json: { error: { code: "QUIZ_ATTEMPT_LIMIT", message: "Bạn đã dùng hết số lần làm bài", details: {}, request_id: null } },
          }),
      },
    });
    await page.reload();
    await expect(page.getByText("Bạn đã dùng hết số lần làm quiz này.")).toBeVisible();
  });
});
