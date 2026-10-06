import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it } from "vitest";
import { api, server } from "@/test/msw";
import { lastAttempt } from "./attempt-store";
import { useQuizAttempt } from "./use-quiz-attempt";

const attempt = {
  id: "at-1",
  quiz_id: "qz-1",
  attempt_no: 1,
  status: "in_progress",
  started_at: "2026-10-06T00:00:00Z",
  deadline_at: null,
  questions: [
    { id: "q1", stem: "Câu 1?", options: [{ id: "A", text: "a" }, { id: "B", text: "b" }] },
    { id: "q2", stem: "Câu 2?", options: [{ id: "A", text: "a" }, { id: "B", text: "b" }] },
  ],
  answers: { q1: "B" }, // đã lưu từ lần mở trước
};

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return renderHook(() => useQuizAttempt("qz-1"), { wrapper });
}

describe("useQuizAttempt", () => {
  it("tiếp tục bài làm dở (200) với đáp án đã lưu, chọn đáp án thì tự lưu, nộp kèm final_answers", async () => {
    const saved: unknown[] = [];
    let submitted: unknown = null;
    server.use(
      http.post(api("/quizzes/qz-1/attempts"), () => HttpResponse.json(attempt, { status: 200 })),
      http.put(api("/attempts/at-1/answers/:qid"), async ({ params, request }) => {
        saved.push({ q: params.qid, ...(await request.json() as object) });
        return HttpResponse.json({ question_id: params.qid, selected_option_id: "A", answered_at: "2026-10-06T00:00:01Z" });
      }),
      http.post(api("/attempts/at-1/submit"), async ({ request }) => {
        submitted = await request.json();
        return HttpResponse.json({
          attempt_id: "at-1", quiz_id: "qz-1", attempt_no: 1, status: "completed", score: 50, passed: true,
          correct_count: 1, total: 2, submitted_at: "2026-10-06T00:01:00Z", questions: [],
        });
      }),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.answers).toEqual({ q1: "B" }));
    expect(result.current.saveStates.q1).toBe("saved");

    act(() => result.current.select("q2", "A"));
    expect(result.current.saveStates.q2).toBe("saving");
    await waitFor(() => expect(result.current.saveStates.q2).toBe("saved"));
    expect(saved).toEqual([{ q: "q2", selected_option_id: "A" }]);

    let res: Awaited<ReturnType<typeof result.current.submit>> | undefined;
    await act(async () => {
      res = await result.current.submit();
    });
    expect(res?.score).toBe(50);
    expect(submitted).toEqual({
      final_answers: [
        { question_id: "q1", selected_option_id: "B" },
        { question_id: "q2", selected_option_id: "A" },
      ],
    });
    expect(lastAttempt.get("qz-1")).toMatchObject({ attemptId: "at-1", status: "completed", score: 50 });
  });

  it("hết lượt làm bài → lỗi QUIZ_ATTEMPT_LIMIT để giao diện hiện thông báo", async () => {
    server.use(
      http.post(api("/quizzes/qz-1/attempts"), () =>
        HttpResponse.json(
          { error: { code: "QUIZ_ATTEMPT_LIMIT", message: "Bạn đã dùng hết số lần làm bài", details: {}, request_id: null } },
          { status: 409 },
        ),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.attempt.isError).toBe(true));
    expect(result.current.attempt.error).toMatchObject({ code: "QUIZ_ATTEMPT_LIMIT" });
  });
});

// Lệch plan (P2, người dùng duyệt): bài đã nộp ở tab/thiết bị khác → server trả 409 ATTEMPT_CLOSED
describe("useQuizAttempt — bài đã đóng (ATTEMPT_CLOSED)", () => {
  const closedBody = { error: { code: "ATTEMPT_CLOSED", message: "Bài làm đã được nộp", details: {}, request_id: null } };

  it("lưu đáp án bị 409 ATTEMPT_CLOSED → closed = true, kèm attemptId để chuyển sang trang kết quả", async () => {
    server.use(
      http.post(api("/quizzes/qz-1/attempts"), () => HttpResponse.json(attempt, { status: 200 })),
      http.put(api("/attempts/at-1/answers/:qid"), () => HttpResponse.json(closedBody, { status: 409 })),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.attemptId).toBe("at-1"));
    expect(result.current.closed).toBe(false);

    act(() => result.current.select("q2", "A"));
    await waitFor(() => expect(result.current.closed).toBe(true));
    expect(result.current.saveStates.q2).toBe("error");
    expect(result.current.attemptId).toBe("at-1");
  });

  it("nộp bài bị 409 ATTEMPT_CLOSED → closed = true và submit() reject với lỗi đó", async () => {
    server.use(
      http.post(api("/quizzes/qz-1/attempts"), () => HttpResponse.json(attempt, { status: 200 })),
      http.post(api("/attempts/at-1/submit"), () => HttpResponse.json(closedBody, { status: 409 })),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.attemptId).toBe("at-1"));

    await act(async () => {
      await expect(result.current.submit()).rejects.toMatchObject({ code: "ATTEMPT_CLOSED" });
    });
    expect(result.current.closed).toBe(true);
  });
});
