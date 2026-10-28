import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api as url, server } from "@/test/msw";
import { LessonQuizzes } from "./lesson-quizzes";

type Last = { id: string; attempt_no: number; status: "in_progress" | "completed" | "timed_out"; score: number | null; expired: boolean };

const quiz = (id: string, used: number, last: Last | null, max_attempts = 2) => ({
  id,
  lesson_id: "l1",
  title: `Quiz ${id}`,
  max_attempts,
  pass_score: 50,
  time_limit_sec: null,
  shuffle: false,
  status: "published",
  question_count: 3,
  created_at: "2026-10-01T00:00:00Z",
  attempts_used: used,
  my_last_attempt: last,
});

function setup(items: ReturnType<typeof quiz>[]) {
  server.use(http.get(url("/quizzes"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 50 })));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <LessonQuizzes slug="khoa" lessonId="l1" isStudent />
    </QueryClientProvider>,
  );
}

const base = (id: string) => `/learn/khoa/l1/quiz/${id}`;

describe("LessonQuizzes (lượt làm gần nhất lấy từ server)", () => {
  it("chưa làm: Làm bài; đang làm dở: Làm tiếp; đã nộp: điểm gần nhất + Làm lại", async () => {
    setup([
      quiz("a", 0, null),
      quiz("b", 1, { id: "at-b", attempt_no: 1, status: "in_progress", score: null, expired: false }),
      quiz("c", 1, { id: "at-c", attempt_no: 1, status: "completed", score: 66.67, expired: false }),
    ]);
    expect(await screen.findByRole("link", { name: /Làm bài/ })).toHaveAttribute("href", base("a"));
    expect(screen.getByRole("link", { name: /Làm tiếp/ })).toHaveAttribute("href", base("b"));
    expect(screen.getByRole("link", { name: "Điểm gần nhất 66.7%" })).toHaveAttribute("href", `${base("c")}/result/at-c`);
    expect(screen.getByRole("link", { name: /Làm lại/ })).toHaveAttribute("href", base("c"));
  });

  it("bài dở đã quá giờ: không còn Làm tiếp, có Xem kết quả; hết lượt thì báo Đã hết lượt", async () => {
    setup([quiz("d", 1, { id: "at-d", attempt_no: 1, status: "in_progress", score: null, expired: true }, 1)]);
    expect(await screen.findByRole("link", { name: "Xem kết quả" })).toHaveAttribute("href", `${base("d")}/result/at-d`);
    expect(screen.queryByRole("link", { name: /Làm tiếp/ })).toBeNull();
    expect(screen.getByText("Đã hết lượt")).toBeInTheDocument();
  });
});
