import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it } from "vitest";
import { api, server } from "@/test/msw";
import { useTutorChat } from "./use-tutor-chat";
import { fireEvent, render, screen } from "@testing-library/react";
import { TutorPanel } from "@/components/tutor/tutor-panel";

function sse(events: [string, unknown][]) {
  const body = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
  return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
}

function setup() {
  server.use(
    http.get(api("/tutor/availability"), () => HttpResponse.json({ available: true, ready_chunks: 5, message: null })),
    http.get(api("/tutor/sessions"), () => HttpResponse.json({ items: [], total: 0, page: 1, size: 20 })),
    http.post(api("/tutor/sessions"), () =>
      HttpResponse.json({ id: "s1", course_id: "c1", lesson_id: "l1", created_at: "2026-10-01T00:00:00Z" }, { status: 201 }),
    ),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper });
}

const source = { n: 1, chunk_id: "k1", lesson_id: "l1", page_no: 3, start_sec: null, lesson_title: "Bài 1", heading_path: "Đạo hàm", snippet: "..." };

describe("useTutorChat", () => {
  it("stream: nguồn hiện trước, token nối dần, done thay bằng nội dung cuối", async () => {
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () =>
        sse([
          ["sources", { sources: [source] }],
          ["token", { text: "Đạo hàm là " }],
          ["token", { text: "giới hạn [1]" }],
          ["done", { message_id: "m9", content: "Đạo hàm là giới hạn [1].", citations: [source], refused: false }],
        ]),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    await act(() => result.current.send("Đạo hàm là gì?"));
    const [q, a] = result.current.messages;
    expect(q).toMatchObject({ role: "user", content: "Đạo hàm là gì?" });
    expect(a).toMatchObject({ id: "m9", status: "done", content: "Đạo hàm là giới hạn [1]." });
    expect(a.sources).toHaveLength(1);
  });

  it("event error (kể cả là event đầu tiên) → trạng thái lỗi kèm câu dễ hiểu", async () => {
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () =>
        sse([["error", { code: "AI_UNAVAILABLE", message: "AI đang bận" }]]),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    await act(() => result.current.send("Hỏi"));
    expect(result.current.messages[1]).toMatchObject({ status: "error", error: "AI đang bận" });
    expect(result.current.busy).toBe(false);
  });

  it("429 trước khi stream → lỗi + mốc thời gian được hỏi lại", async () => {
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () =>
        HttpResponse.json(
          { error: { code: "RATE_LIMITED", message: "Chậm lại", details: {}, request_id: null } },
          { status: 429, headers: { "Retry-After": "40" } },
        ),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    await act(() => result.current.send("Hỏi"));
    expect(result.current.messages[1].error).toMatch(/40 giây/);
    expect(result.current.retryAt).toBeGreaterThan(Date.now());
  });
});

// ---- Lệch plan: test cho các bản sửa đã duyệt (reset theo phạm vi, khóa ô nhập khi đang tải lịch sử,
// size=100 khi tìm phiên, "stopped" khi stream kết thúc sau abort, nhả body khi thoát sớm) ----

const enc = new TextEncoder();

/** Stream SSE điều khiển bằng tay; ghi lại việc body bị hủy hoặc request bị abort. */
function controlledStream() {
  let ctrl!: ReadableStreamDefaultController<Uint8Array>;
  const state = { cancelled: false, aborted: false };
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      ctrl = c;
    },
    cancel() {
      state.cancelled = true;
    },
  });
  const pushRaw = (raw: string) => {
    try {
      ctrl.enqueue(enc.encode(raw));
    } catch {
      // stream đã đóng/hủy
    }
  };
  const push = (e: string, d: unknown) => pushRaw(`event: ${e}\ndata: ${JSON.stringify(d)}\n\n`);
  const close = () => {
    try {
      ctrl.close();
    } catch {
      // đã đóng/hủy
    }
  };
  const respond = (request: Request) => {
    request.signal.addEventListener("abort", () => {
      state.aborted = true;
    });
    return new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream" } });
  };
  return { state, push, pushRaw, close, respond };
}

function baseHandlers(onSessions?: (url: URL) => void) {
  server.use(
    http.get(api("/tutor/availability"), () => HttpResponse.json({ available: true, ready_chunks: 5, message: null })),
    http.get(api("/tutor/sessions"), ({ request }) => {
      onSessions?.(new URL(request.url));
      return HttpResponse.json({
        items: [{ id: "s2", course_id: "c1", lesson_id: "l2", created_at: "2026-10-01T00:00:00Z" }],
        total: 1,
        page: 1,
        size: 100,
      });
    }),
    http.get(api("/tutor/sessions/s2/messages"), () =>
      HttpResponse.json({
        items: [
          {
            id: "h1",
            role: "user",
            content: "Câu cũ bài 2",
            citations: [],
            refused: false,
            truncated: false,
            feedback: null,
            created_at: "2026-10-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        size: 100,
      }),
    ),
    http.post(api("/tutor/sessions"), () =>
      HttpResponse.json({ id: "s1", course_id: "c1", lesson_id: "l1", created_at: "2026-10-01T00:00:00Z" }, { status: 201 }),
    ),
  );
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useTutorChat (bản sửa sau review)", () => {
  it("đổi bài: abort stream đang chạy, xóa hội thoại cũ, tải lịch sử bài mới; stream cũ không vá vào bài mới", async () => {
    baseHandlers();
    const s = controlledStream();
    server.use(http.post(api("/tutor/sessions/s1/messages"), ({ request }) => s.respond(request)));
    const { result, rerender } = renderHook(({ lessonId }) => useTutorChat({ courseId: "c1", lessonId }), {
      wrapper: makeWrapper(),
      initialProps: { lessonId: "l1" as string | null },
    });
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.send("Hỏi bài 1");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));
    s.push("sources", { sources: [source] });
    await waitFor(() => expect(result.current.messages[1]?.sources).toHaveLength(1));

    rerender({ lessonId: "l2" });
    expect(result.current.messages).toEqual([]);
    expect(result.current.busy).toBe(false);
    expect(result.current.retryAt).toBeNull();
    expect(result.current.loadingHistory).toBe(true);
    await waitFor(() => expect(result.current.messages.map((m) => m.content)).toEqual(["Câu cũ bài 2"]));
    await waitFor(() => expect(s.state.aborted || s.state.cancelled).toBe(true));

    // stream cũ cố gửi tiếp: không được đụng vào hội thoại bài 2
    s.push("token", { text: "rò rỉ" });
    s.close();
    await act(() => pending);
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({ id: "h1", content: "Câu cũ bài 2", status: "done" });
    expect(result.current.busy).toBe(false);
  });

  it("unmount: abort stream đang chạy", async () => {
    baseHandlers();
    const s = controlledStream();
    server.use(http.post(api("/tutor/sessions/s1/messages"), ({ request }) => s.respond(request)));
    const { result, unmount } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.send("Hỏi");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));
    s.push("sources", { sources: [source] });
    await waitFor(() => expect(result.current.messages[1]?.sources).toHaveLength(1));
    unmount();
    await waitFor(() => expect(s.state.aborted || s.state.cancelled).toBe(true));
    s.close();
    await pending;
  });

  it("tìm phiên với size=100", async () => {
    let size: string | null = null;
    baseHandlers((url) => (size = url.searchParams.get("size")));
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    expect(size).toBe("100");
  });

  it("panel: ô nhập và nút Gửi bị khóa khi đang tải lịch sử", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    baseHandlers();
    server.use(
      http.get(api("/tutor/sessions"), async () => {
        await gate;
        return HttpResponse.json({ items: [], total: 0, page: 1, size: 100 });
      }),
    );
    function Harness() {
      const chat = useTutorChat({ courseId: "c1", lessonId: "l1" });
      return <TutorPanel chat={chat} lessonId="l1" />;
    }
    render(<Harness />, { wrapper: makeWrapper() });
    const input = screen.getByLabelText("Câu hỏi cho AI Tutor");
    fireEvent.change(input, { target: { value: "Hỏi sớm" } });
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: /Gửi/ })).toBeDisabled();
    await act(async () => release());
    await waitFor(() => expect(input).toBeEnabled());
    expect(screen.getByRole("button", { name: /Gửi/ })).toBeEnabled();
  });

  it("bấm Dừng: stream kết thúc sau abort → 'stopped', không còn 'streaming'", async () => {
    baseHandlers();
    const s = controlledStream();
    server.use(http.post(api("/tutor/sessions/s1/messages"), ({ request }) => s.respond(request)));
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.send("Hỏi");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));
    s.push("token", { text: "Đang trả lời" });
    await waitFor(() => expect(result.current.messages[1]?.content).toBe("Đang trả lời"));
    act(() => result.current.stop());
    s.push("token", { text: " tiếp" });
    s.close();
    await act(() => pending);
    expect(result.current.messages[1]).toMatchObject({ status: "stopped", truncated: true });
    expect(result.current.busy).toBe(false);
  });

  it("data hỏng giữa stream → lỗi (không phải 'stopped') và body được nhả", async () => {
    baseHandlers();
    const s = controlledStream();
    server.use(http.post(api("/tutor/sessions/s1/messages"), ({ request }) => s.respond(request)));
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loadingHistory).toBe(false));
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.send("Hỏi");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));
    s.push("token", { text: "Một phần" });
    await waitFor(() => expect(result.current.messages[1]?.content).toBe("Một phần"));
    s.pushRaw("event: token\ndata: {hỏng\n\n"); // data không phải JSON, stream vẫn mở
    await act(() => pending);
    expect(result.current.messages[1].status).toBe("error");
    expect(result.current.busy).toBe(false);
    await waitFor(() => expect(s.state.aborted || s.state.cancelled).toBe(true));
  });
});
