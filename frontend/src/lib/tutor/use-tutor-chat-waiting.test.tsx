import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TutorPanel } from "@/components/tutor/tutor-panel";
import { api, server } from "@/test/msw";
import { useTutorChat, WAIT_POLL_MS } from "./use-tutor-chat";

const PROCESSING = {
  available: false,
  ready_chunks: 0,
  message: "Tài liệu đang được xử lý (1 tài liệu). Bạn vẫn có thể đặt câu hỏi: AI sẽ trả lời ngay khi xử lý xong.",
  state: "processing",
  processing_docs: 1,
  can_queue: true,
};
const FAILED = {
  available: false,
  ready_chunks: 0,
  message: "Tài liệu xử lý không thành công.",
  state: "failed",
  processing_docs: 0,
  can_queue: false,
};

function msg(id: string, role: "user" | "assistant", content: string, waiting = false) {
  return {
    id,
    role,
    content,
    citations: [],
    refused: false,
    truncated: false,
    feedback: null,
    waiting_for_docs: waiting,
    created_at: "2026-10-12T00:00:00Z",
  };
}

function handlers(availability: object) {
  server.use(
    http.get(api("/tutor/availability"), () => HttpResponse.json(availability)),
    http.get(api("/tutor/sessions"), () => HttpResponse.json({ items: [], total: 0, page: 1, size: 100 })),
    http.post(api("/tutor/sessions"), () =>
      HttpResponse.json({ id: "s1", course_id: "c1", lesson_id: "l1", created_at: "2026-10-12T00:00:00Z" }, { status: 201 }),
    ),
  );
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

afterEach(() => vi.useRealTimers());

describe("useTutorChat: hỏi lúc tài liệu đang xử lý", () => {
  it("gửi câu hỏi chờ qua /questions (không mở stream), câu hỏi hiện trạng thái chờ", async () => {
    handlers(PROCESSING);
    let streamed = false;
    let body: unknown = null;
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () => {
        streamed = true;
        return HttpResponse.json({});
      }),
      http.post(api("/tutor/sessions/s1/questions"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(msg("q1", "user", "Đạo hàm là gì?", true), { status: 202 });
      }),
    );
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.availability?.can_queue).toBe(true));
    await act(() => result.current.send("Đạo hàm là gì?"));
    expect(body).toEqual({ content: "Đạo hàm là gì?" });
    expect(streamed).toBe(false);
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({ id: "q1", role: "user", status: "waiting" });
  });

  it("409 khi gửi câu chờ → báo lỗi ngay dưới câu hỏi", async () => {
    handlers(PROCESSING);
    server.use(
      http.post(api("/tutor/sessions/s1/questions"), () =>
        HttpResponse.json(
          { error: { code: "TOO_MANY_WAITING", message: "Bạn đã có 5 câu hỏi đang chờ" } },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.availability?.can_queue).toBe(true));
    await act(() => result.current.send("Câu thứ sáu"));
    expect(result.current.messages[0]).toMatchObject({ status: "error", error: "Bạn đã có 5 câu hỏi đang chờ" });
  });

  it("câu chờ được trả lời: hỏi lại định kỳ rồi thay bằng câu trả lời của server", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    handlers(PROCESSING);
    let answered = false;
    server.use(
      http.get(api("/tutor/sessions"), () =>
        HttpResponse.json({
          items: [{ id: "s1", course_id: "c1", lesson_id: "l1", created_at: "2026-10-12T00:00:00Z" }],
          total: 1,
          page: 1,
          size: 100,
        }),
      ),
      http.get(api("/tutor/sessions/s1/messages"), () =>
        HttpResponse.json({
          items: answered
            ? [msg("q1", "user", "Đạo hàm là gì?"), msg("a1", "assistant", "Là giới hạn [1].")]
            : [msg("q1", "user", "Đạo hàm là gì?", true)],
          total: answered ? 2 : 1,
          page: 1,
          size: 100,
        }),
      ),
    );
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.messages[0]?.status).toBe("waiting"));
    await act(() => vi.advanceTimersByTimeAsync(WAIT_POLL_MS));
    expect(result.current.messages).toHaveLength(1); // chưa trả lời: giữ nguyên
    answered = true;
    await act(() => vi.advanceTimersByTimeAsync(WAIT_POLL_MS));
    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    expect(result.current.messages[0].status).toBe("done");
    expect(result.current.messages[1]).toMatchObject({ id: "a1", role: "assistant", content: "Là giới hạn [1]." });
  });
});

describe("TutorPanel: trạng thái tài liệu", () => {
  function Harness() {
    const chat = useTutorChat({ courseId: "c1", lessonId: "l1" });
    return <TutorPanel chat={chat} lessonId="l1" />;
  }

  it("đang xử lý: vẫn nhập và gửi được, có lời nhắn AI sẽ trả lời sau", async () => {
    handlers(PROCESSING);
    render(<Harness />, { wrapper: wrapper() });
    expect(await screen.findByText(/AI sẽ trả lời ngay khi xử lý xong/)).toBeInTheDocument();
    const input = screen.getByLabelText("Câu hỏi cho AI Tutor");
    await waitFor(() => expect(input).toBeEnabled());
    expect(input).toHaveAttribute("placeholder", expect.stringMatching(/khi tài liệu xử lý xong/));
    fireEvent.change(input, { target: { value: "Hỏi trước" } });
    expect(screen.getByRole("button", { name: /Gửi/ })).toBeEnabled();
  });

  it("xử lý lỗi: hiện đúng lý do, khóa ô nhập", async () => {
    handlers(FAILED);
    render(<Harness />, { wrapper: wrapper() });
    expect(await screen.findByText("Tài liệu xử lý không thành công.")).toBeInTheDocument();
    expect(screen.getByLabelText("Câu hỏi cho AI Tutor")).toBeDisabled();
  });
});
