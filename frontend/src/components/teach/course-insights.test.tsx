import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api as url, server } from "@/test/msw";
import { CourseInsightsSection } from "./course-insights";

function setup(body: Record<string, unknown>) {
  server.use(http.get(url("/courses/c1/insights"), () => HttpResponse.json({ course_id: "c1", min_answers: 3, ...body })));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CourseInsightsSection slug="khoa" courseId="c1" />
    </QueryClientProvider>,
  );
}

describe("CourseInsightsSection", () => {
  it("câu hay sai dẫn tới ngân hàng câu hỏi của bài, ghi rõ trang tài liệu và phương án hay chọn nhầm", async () => {
    setup({
      hard_questions: [
        {
          question_id: "q1",
          stem: "TCP khác UDP ở điểm nào?",
          lesson_id: "l1",
          lesson_title: "Tầng giao vận",
          answers: 4,
          wrong: 3,
          wrong_rate: 0.75,
          correct_option: "B",
          top_wrong: { id: "C", text: "…", count: 2 },
          source_page: 12,
        },
      ],
      weak_lessons: [
        { lesson_id: "l1", title: "Tầng giao vận", section_title: "Chương 2", attempts: 4, avg_score: 37.5, tutor_questions: 6 },
      ],
      students_at_risk: [
        {
          user_id: "u1",
          full_name: "Trần Thị Mai",
          progress_pct: 20,
          avg_score: 30,
          last_active_at: new Date(Date.now() - 9 * 86400_000).toISOString(),
          reasons: ["Điểm quiz trung bình 30%", "Không học 9 ngày"],
        },
      ],
    });
    const link = await screen.findByRole("link", { name: /TCP khác UDP/ });
    expect(link).toHaveAttribute("href", "/teach/khoa/lessons/l1/questions");
    expect(link).toHaveTextContent("tài liệu trang 12");
    expect(link).toHaveTextContent("hay chọn nhầm C (2 lượt)");
    expect(link).toHaveTextContent("75% sai");
    expect(screen.getByRole("cell", { name: "37.5%" })).toBeInTheDocument();
    expect(screen.getByText("Học viên cần để ý (1)")).toBeInTheDocument();
    expect(screen.getByText("Không học 9 ngày")).toBeInTheDocument();
    expect(screen.getByText("học lần cuối 9 ngày trước")).toBeInTheDocument();
  });

  it("chưa đủ số liệu: mỗi phần có câu giải thích thay vì bảng trống", async () => {
    setup({ hard_questions: [], weak_lessons: [], students_at_risk: [] });
    expect(await screen.findByText("Chưa đủ lượt làm bài để xếp hạng.")).toBeInTheDocument();
    expect(screen.getByText("Chưa có bài nào có số liệu.")).toBeInTheDocument();
    expect(screen.getByText("Không có học viên nào cần để ý lúc này.")).toBeInTheDocument();
  });
});
