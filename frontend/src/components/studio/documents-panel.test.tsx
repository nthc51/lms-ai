import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { canAskTutor } from "@/lib/tutor/use-tutor-chat";
import { DocumentsPanel } from "./documents-panel";

// Lệch plan (5c): câu hỏi gợi ý ở tab Tài liệu không được gửi khi AI Tutor chưa sẵn sàng (fix B của FE-1).
function setup(disabled: boolean) {
  server.use(
    http.get(url("/lessons/l1/documents"), () =>
      HttpResponse.json([
        {
          source_id: "s1",
          title: "Giáo trình",
          page_count: 12,
          guide: { status: "ready", title: "Giáo trình", summary: "Tóm tắt", topics: ["Đạo hàm"], questions: ["Đạo hàm là gì?"] },
        },
      ]),
    ),
  );
  const onAsk = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <DocumentsPanel lessonId="l1" onAsk={onAsk} disabled={disabled} />
    </QueryClientProvider>,
  );
  return { onAsk, user: userEvent.setup() };
}

describe("DocumentsPanel", () => {
  it("bấm câu hỏi gợi ý thì hỏi AI Tutor", async () => {
    const { onAsk, user } = setup(false);
    await user.click(await screen.findByRole("button", { name: "Đạo hàm là gì?" }));
    expect(onAsk).toHaveBeenCalledWith("Đạo hàm là gì?");
  });

  it("disabled: nút câu hỏi bị khóa, không gửi", async () => {
    const { onAsk, user } = setup(true);
    const btn = await screen.findByRole("button", { name: "Đạo hàm là gì?" });
    expect(btn).toBeDisabled();
    await user.click(btn);
    expect(onAsk).not.toHaveBeenCalled();
  });
});

describe("canAskTutor", () => {
  it("chỉ cho hỏi khi không bận, đã tải lịch sử và không đếm ngược 429", () => {
    expect(canAskTutor({ busy: false, loadingHistory: false, retryAt: null })).toBe(true);
    expect(canAskTutor({ busy: true, loadingHistory: false, retryAt: null })).toBe(false);
    expect(canAskTutor({ busy: false, loadingHistory: true, retryAt: null })).toBe(false);
    expect(canAskTutor({ busy: false, loadingHistory: false, retryAt: Date.now() + 5000 })).toBe(false);
  });
});
