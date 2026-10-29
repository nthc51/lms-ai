import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { assignment } from "@/components/assignment/fixtures";
import { api as url, server } from "@/test/msw";
import { SubmissionReview } from "./submission-review";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/teach/khoa/lessons/l1/assignments/as-1",
  useSearchParams: () => new URLSearchParams("bai=sub-1"),
}));

const detail = (over: Record<string, unknown> = {}) => ({
  id: "sub-1",
  assignment_id: "as-1",
  user_id: "u1",
  student_name: "Lê Minh Châu",
  status: "ai_graded",
  version: 1,
  submitted_at: "2026-10-29T01:00:00Z",
  text_content: "Tìm kiếm nhị phân chia đôi mảng.",
  file: null,
  file_url: null,
  ai_result: {
    scores: {
      c1: { score: 4, justification: "Đúng ý chính", evidence_quote: "chia đôi mảng", evidence_found: true },
      c2: { score: 3, justification: "Gọn", evidence_quote: "câu bịa", evidence_found: false },
    },
    feedback: "Bài khá tốt.",
    total: 7,
    model: "fake",
    prompt_version: "assignment_grade@v1",
    version: 1,
  },
  ai_error: null,
  final_scores: null,
  final_total: null,
  teacher_feedback: null,
  graded_at: null,
  ...over,
});

function setup() {
  const graded: unknown[] = [];
  server.use(
    http.get(url("/assignments/as-1"), () => HttpResponse.json(assignment({ submission_count: 1, to_review: 1 }))),
    http.get(url("/assignments/as-1/submissions"), () =>
      HttpResponse.json({
        items: [{ id: "sub-1", user_id: "u1", student_name: "Lê Minh Châu", status: "ai_graded", version: 1, submitted_at: "2026-10-29T01:00:00Z", ai_total: 7, final_total: null, flagged: 1 }],
        total: 1,
        page: 1,
        size: 20,
      }),
    ),
    http.get(url("/submissions/sub-1"), () => HttpResponse.json(detail())),
    http.post(url("/submissions/sub-1/grade"), async ({ request }) => {
      graded.push(await request.json());
      return HttpResponse.json(detail({ status: "graded", final_scores: { c1: 5, c2: 3 }, final_total: 8 }));
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SubmissionReview slug="khoa" lessonId="l1" assignmentId="as-1" />
    </QueryClientProvider>,
  );
  return { graded };
}

describe("SubmissionReview", () => {
  it("điền sẵn điểm và nhận xét AI gợi ý, gắn cờ câu trích không có trong bài, xác nhận gửi điểm của giảng viên", async () => {
    const user = userEvent.setup();
    const { graded } = setup();
    expect(await screen.findByText(/1 trích dẫn cần xem/)).toBeInTheDocument();
    const c1 = await screen.findByLabelText("Điểm Đúng khái niệm");
    expect(c1).toHaveValue(4);
    expect(screen.getByLabelText("Điểm Trình bày")).toHaveValue(3);
    expect(screen.getByLabelText(/Nhận xét cho học viên/)).toHaveValue("Bài khá tốt.");
    expect(screen.getByText(/Không tìm thấy câu trích này trong bài làm/)).toBeInTheDocument();
    expect(screen.getByText("Tổng: 7/10")).toBeInTheDocument();

    await user.clear(c1);
    await user.type(c1, "9");
    await user.click(screen.getByRole("button", { name: "Xác nhận điểm" }));
    expect(screen.getByRole("alert")).toHaveTextContent("phải từ 0 đến 6");
    await user.clear(c1);
    await user.type(c1, "5");
    await user.click(screen.getByRole("button", { name: "Xác nhận điểm" }));
    await waitFor(() => expect(graded).toEqual([{ scores: { c1: 5, c2: 3 }, feedback: "Bài khá tốt." }]));
    expect(await screen.findByRole("button", { name: "Cập nhật điểm" })).toBeInTheDocument();
  });
});
