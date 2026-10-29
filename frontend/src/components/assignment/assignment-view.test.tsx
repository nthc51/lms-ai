import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { AssignmentView } from "./assignment-view";
import { assignment, mySubmission } from "./fixtures";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

function setup(data: Record<string, unknown>) {
  let current = data;
  const sent: unknown[] = [];
  server.use(
    http.get(url("/assignments/as-1"), () => HttpResponse.json(current)),
    http.put(url("/assignments/as-1/submission"), async ({ request }) => {
      sent.push(await request.json());
      current = { ...current, my_submission: mySubmission() };
      return HttpResponse.json(current.my_submission as Record<string, unknown>);
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AssignmentView id="as-1" />
    </QueryClientProvider>,
  );
  return { sent };
}

describe("AssignmentView (học viên)", () => {
  it("chưa nộp: thấy đề, rubric và nút về bài học; nộp bài gửi nội dung, xong thì thấy Đã nộp bài", async () => {
    const user = userEvent.setup();
    const { sent } = setup(assignment());
    expect(await screen.findByRole("heading", { name: "Bài tập tìm kiếm nhị phân", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Tìm kiếm/ })).toHaveAttribute("href", "/learn/khoa/l1");
    expect(screen.getByText("Đúng khái niệm")).toBeInTheDocument();
    expect(screen.getByText("Không có hạn nộp · 10 điểm")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Nộp bài" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bài làm trống");
    await user.type(screen.getByLabelText("Bài làm"), "Chia đôi mảng đã sắp xếp");
    await user.click(screen.getByRole("button", { name: "Nộp bài" }));
    await waitFor(() => expect(sent).toEqual([{ text_content: "Chia đôi mảng đã sắp xếp", asset_id: null }]));
    expect(await screen.findByRole("heading", { name: "Đã nộp bài" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nộp lại" })).toBeInTheDocument();
  });

  it("đã có điểm: thấy tổng điểm, điểm từng tiêu chí và nhận xét; không còn nút nộp lại", async () => {
    setup(
      assignment({
        my_submission: mySubmission({
          status: "graded",
          final_scores: { c1: 5.5, c2: 4 },
          final_total: 9.5,
          teacher_feedback: "Bài tốt",
        }),
      }),
    );
    expect(await screen.findByRole("heading", { name: "Kết quả" })).toBeInTheDocument();
    expect(screen.getByText("9.5")).toBeInTheDocument();
    expect(screen.getByText("5.5/6 điểm")).toBeInTheDocument();
    expect(screen.getByText("Bài tốt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Nộp/ })).toBeNull();
  });

  it("quá hạn mà chưa nộp: báo hết hạn, không có ô nộp", async () => {
    setup(assignment({ due_at: "2020-01-01T00:00:00Z" }));
    expect(await screen.findByText("Đã hết hạn nộp bài.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Bài làm")).toBeNull();
  });
});
