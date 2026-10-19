import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { LessonDiscussion } from "./lesson-discussion";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const comment = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  parent_id: null,
  body: `Câu hỏi ${id}`,
  deleted: false,
  author_name: "Bình",
  author_role: "student",
  is_course_teacher: false,
  can_delete: false,
  created_at: new Date().toISOString(),
  replies: [],
  ...over,
});

function setup(items: ReturnType<typeof comment>[], total = items.length) {
  const posted: unknown[] = [];
  const deleted: string[] = [];
  server.use(
    http.get(url("/lessons/l1/comments"), ({ request }) => {
      const page = Number(new URL(request.url).searchParams.get("page") ?? 1);
      const slice = page === 1 ? items : [comment("trang2")];
      return HttpResponse.json({ items: slice, total, page, size: 10 });
    }),
    http.post(url("/lessons/l1/comments"), async ({ request }) => {
      posted.push(await request.json());
      return HttpResponse.json(comment("moi"), { status: 201 });
    }),
    http.delete(url("/comments/:id"), ({ params }) => {
      deleted.push(params.id as string);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <LessonDiscussion lessonId="l1" />
    </QueryClientProvider>,
  );
  return { posted, deleted };
}

describe("LessonDiscussion", () => {
  it("chưa có gì: mời đặt câu hỏi; gửi thì nút khóa khi ô trống và gửi nội dung đã cắt khoảng trắng", async () => {
    const user = userEvent.setup();
    const { posted } = setup([]);
    expect(await screen.findByText(/Chưa có thảo luận nào/)).toBeInTheDocument();
    const send = screen.getByRole("button", { name: "Gửi" });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText("Đặt câu hỏi hoặc chia sẻ về bài này"), "  Em chưa hiểu phần 2  ");
    await user.click(send);
    await waitFor(() => expect(posted).toEqual([{ body: "Em chưa hiểu phần 2" }]));
    expect(screen.getByLabelText("Đặt câu hỏi hoặc chia sẻ về bài này")).toHaveValue("");
  });

  it("hiện nhãn Giảng viên ở câu trả lời, bình luận đã xóa và trả lời một cấp", async () => {
    const user = userEvent.setup();
    const { posted } = setup([
      comment("c1", {
        replies: [comment("r1", { parent_id: "c1", author_name: "Cô Lan", author_role: "teacher", is_course_teacher: true, body: "Xem trang 3 nhé" })],
      }),
      comment("c2", { deleted: true, body: null }),
    ]);
    expect(await screen.findByText("Câu hỏi c1")).toBeInTheDocument();
    const replies = screen.getByRole("list", { name: "Trả lời cho Bình" });
    expect(within(replies).getByText("Giảng viên")).toBeInTheDocument();
    expect(screen.getByText("Bình luận đã bị xóa.")).toBeInTheDocument();
    // bình luận đã xóa không có nút Trả lời: chỉ c1 có
    const replyButtons = screen.getAllByRole("button", { name: "Trả lời" });
    expect(replyButtons).toHaveLength(1);
    await user.click(replyButtons[0]);
    await user.type(screen.getByLabelText("Trả lời Bình"), "Dạ em hiểu rồi");
    await user.click(screen.getByRole("button", { name: "Gửi trả lời" }));
    await waitFor(() => expect(posted).toEqual([{ body: "Dạ em hiểu rồi", parent_id: "c1" }]));
  });

  it("xóa cần xác nhận; 'Xem thêm' tải trang kế", async () => {
    const user = userEvent.setup();
    const { deleted } = setup([comment("c1", { can_delete: true })], 11);
    await user.click(await screen.findByRole("button", { name: "Xóa bình luận của Bình" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(deleted).toEqual(["c1"]));
    await user.click(screen.getByRole("button", { name: "Xem thêm thảo luận" }));
    expect(await screen.findByText("Câu hỏi trang2")).toBeInTheDocument();
  });
});
