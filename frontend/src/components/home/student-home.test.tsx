import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { lastLesson, scrollPosition } from "@/lib/study/storage";
import { api as url, server } from "@/test/msw";

vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ status: "authenticated" }) }));

import { StudentHome } from "./student-home";

const course = (n: number, over: Record<string, unknown> = {}) => ({
  course_id: `c${n}`,
  title: `Khóa ${n}`,
  slug: `khoa-${n}`,
  enrolled_at: "2026-09-02T00:00:00Z",
  completed_at: null as string | null,
  total_lessons: 12,
  done_lessons: 5,
  progress_pct: 41,
  ...over,
});

const quiz = (over: Record<string, unknown> = {}) => ({
  quiz_id: "q1",
  title: "Kiểm tra chương 3",
  lesson_id: "l-6",
  lesson_title: "Điều chế biên độ",
  course_title: "Khóa 1",
  course_slug: "khoa-1",
  question_count: 10,
  time_limit_sec: 900,
  in_progress: false,
  ...over,
});

function setup(items: ReturnType<typeof course>[], pending: ReturnType<typeof quiz>[] = []) {
  server.use(
    http.get(url("/me/courses"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 20 })),
    http.get(url("/me/pending-quizzes"), () => HttpResponse.json(pending)),
    http.get(url("/lessons/l-6"), () =>
      HttpResponse.json({ id: "l-6", section_id: "s", course_id: "c1", title: "Điều chế biên độ", content_md: "", duration_sec: null, progress: null }),
    ),
  );
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StudentHome givenName="An" />
    </QueryClientProvider>,
  );
}

describe("StudentHome", () => {
  it("khối đang học: tên bài, phần đã đọc, nút Học tiếp vào đúng bài; ba con số; quiz chưa làm", async () => {
    lastLesson.set("c1", "l-6");
    scrollPosition.set("l-6", 0.6);
    setup([course(1), course(2, { completed_at: "2026-10-01T00:00:00Z", done_lessons: 12, progress_pct: 100 })], [quiz(), quiz({ quiz_id: "q2", title: "Quiz 2", in_progress: true, time_limit_sec: null })]);

    expect(screen.getByRole("heading", { name: "Chào An.", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("Điều chế biên độ")).toBeInTheDocument();
    expect(screen.getByText(/đã đọc khoảng 60%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Học tiếp/ })).toHaveAttribute("href", "/learn/khoa-1/l-6");
    expect(screen.getByText(/Còn 7 bài trong khóa Khóa 1/)).toBeInTheDocument();
    // 1 khóa đang học, 17 bài đã xong, 1 khóa hoàn thành
    expect(screen.getByText("khóa đang học").parentElement).toHaveTextContent(/^khóa đang học1$/);
    expect(screen.getByText("bài đã học xong").parentElement).toHaveTextContent(/^bài đã học xong17$/);
    expect(screen.getByText("khóa đã hoàn thành").parentElement).toHaveTextContent(/^khóa đã hoàn thành1$/);

    const next = await screen.findByRole("link", { name: /Kiểm tra chương 3 · Khóa 1/ });
    expect(next).toHaveAttribute("href", "/learn/khoa-1/l-6/quiz/q1");
    expect(next).toHaveTextContent("10 câu · 15 phút · chưa làm");
    expect(screen.getByRole("link", { name: /Quiz 2/ })).toHaveTextContent("không giới hạn giờ · đang làm dở");
  });

  it("chưa đăng ký khóa nào: lời mời khám phá, không có khối đang học hay Việc nên làm tiếp", async () => {
    setup([]);
    expect(await screen.findByText("Bạn chưa đăng ký khóa học nào.")).toBeInTheDocument();
    expect(screen.getByText(/Bạn chưa đăng ký khóa nào/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Học tiếp/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Việc nên làm tiếp" })).not.toBeInTheDocument();
  });
});
