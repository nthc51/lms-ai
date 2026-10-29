import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { assignment } from "@/components/assignment/fixtures";
import { api as url, server } from "@/test/msw";
import { AssignmentManager } from "./assignment-manager";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

function setup(items: ReturnType<typeof assignment>[]) {
  const created: unknown[] = [];
  const updated: unknown[] = [];
  const published: string[] = [];
  server.use(
    http.get(url("/assignments"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 50 })),
    http.post(url("/assignments"), async ({ request }) => {
      created.push(await request.json());
      return HttpResponse.json(assignment({ status: "draft" }), { status: 201 });
    }),
    http.patch(url("/assignments/:id"), async ({ request }) => {
      updated.push(await request.json());
      return HttpResponse.json(assignment());
    }),
    http.post(url("/assignments/:id/publish"), ({ params }) => {
      published.push(params.id as string);
      return HttpResponse.json(assignment());
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AssignmentManager slug="khoa" lessonId="l1" />
    </QueryClientProvider>,
  );
  return { created, updated, published };
}

describe("AssignmentManager", () => {
  it("tạo bài tập: rubric có thêm/bớt tiêu chí, gửi đúng nội dung và hạn nộp trống là null", async () => {
    const user = userEvent.setup();
    const { created } = setup([]);
    await user.click(await screen.findByRole("button", { name: "Tạo bài tập" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Tiêu đề"), "Bài 1");
    await user.type(within(dialog).getByLabelText(/Đề bài/), "Giải thích");
    await user.type(within(dialog).getByLabelText("Tiêu chí 1"), "Đúng");
    await user.click(within(dialog).getByRole("button", { name: "Thêm tiêu chí" }));
    await user.type(within(dialog).getByLabelText("Tiêu chí 2"), "Trình bày");
    expect(within(dialog).getByText("Rubric (2 tiêu chí · tổng 4 điểm)")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Tạo bài tập" }));
    await waitFor(() =>
      expect(created).toEqual([
        {
          lesson_id: "l1",
          title: "Bài 1",
          instructions: "Giải thích",
          due_at: null,
          rubric: [
            { criterion: "Đúng", max_points: 2, description: "" },
            { criterion: "Trình bày", max_points: 2, description: "" },
          ],
        },
      ]),
    );
  });

  it("bài nháp có nút Xuất bản (xác nhận), có link tới trang bài nộp", async () => {
    const user = userEvent.setup();
    const { published } = setup([assignment({ status: "draft", submission_count: 2, to_review: 1 })]);
    expect(await screen.findByText(/2 bài nộp · 1 chờ xác nhận/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Bài nộp" })).toHaveAttribute("href", "/teach/khoa/lessons/l1/assignments/as-1");
    await user.click(screen.getByRole("button", { name: "Xuất bản" }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Xuất bản" }));
    await waitFor(() => expect(published).toEqual(["as-1"]));
  });

  it("sửa bài tập: không đổi hạn nộp thì không gửi lại (giữ phần giây); điểm tối đa trống báo lỗi tiếng Việt", async () => {
    const user = userEvent.setup();
    const { updated } = setup([assignment({ due_at: "2026-11-01T16:59:59Z", submission_count: 0, to_review: 0 })]);
    await user.click(await screen.findByRole("button", { name: /Thao tác với bài tập/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Sửa" }));
    const dialog = await screen.findByRole("dialog");
    const points = within(dialog).getAllByLabelText("Điểm tối đa")[0];
    await user.clear(points);
    expect(points).toHaveValue(null);
    await user.click(within(dialog).getByRole("button", { name: "Lưu" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Điểm tối đa mỗi tiêu chí là số nguyên từ 1 đến 100");
    await user.type(points, "5");
    await user.type(within(dialog).getByLabelText("Tiêu đề"), " (sửa)");
    await user.click(within(dialog).getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(updated).toHaveLength(1));
    expect(updated[0]).not.toHaveProperty("due_at");
    expect(updated[0]).toMatchObject({
      title: "Bài tập tìm kiếm nhị phân (sửa)",
      rubric: [
        { criterion: "Đúng khái niệm", max_points: 5, description: "Nêu đúng điều kiện" },
        { criterion: "Trình bày", max_points: 4, description: "" },
      ],
    });
  });
});
