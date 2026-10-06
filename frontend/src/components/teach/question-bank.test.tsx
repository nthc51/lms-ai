import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { QuestionBank } from "./question-bank";

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

const question = (id: string, review_status = "pending") => ({
  id,
  lesson_id: "l1",
  stem: `Đề bài câu ${id} đủ dài`,
  options: ["A", "B", "C", "D"].map((o) => ({ id: o, text: `Lựa chọn ${o} ${id}` })),
  correct_option_id: "A",
  explanation: "",
  difficulty: "easy",
  origin: "ai",
  review_status,
  self_check_flag: false,
  ai_original: null,
  source_page_no: null,
  source_excerpt: null,
});

function setup(initial = [question("q1")]) {
  let items = initial;
  const patches: { id: string; body: Record<string, unknown> }[] = [];
  let patchReply: () => Response = () => HttpResponse.json(question("x"));
  let jobStatus = "processing";
  server.use(
    http.get(url("/lessons/l1/questions"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 100 })),
    http.patch(url("/questions/:id"), async ({ params, request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      patches.push({ id: params.id as string, body });
      const res = patchReply();
      if (res.ok && body.action === "reject") items = items.map((q) => (q.id === params.id ? { ...q, review_status: "rejected" } : q));
      return res;
    }),
    http.post(url("/lessons/l1/questions/generate"), () => HttpResponse.json({ job_id: "j1" }, { status: 202 })),
    http.get(url("/jobs/j1"), () =>
      HttpResponse.json({ id: "j1", type: "quiz_gen", status: jobStatus, attempts: 1, error_msg: null, finished_at: null }),
    ),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <QuestionBank lessonId="l1" />
    </QueryClientProvider>,
  );
  return {
    view,
    patches,
    setItems: (next: ReturnType<typeof question>[]) => (items = next),
    setPatchReply: (fn: () => Response) => (patchReply = fn),
    setJobStatus: (s: string) => (jobStatus = s),
  };
}

describe("QuestionBank", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    toastMock.mockClear();
    toastMock.success.mockClear();
    toastMock.error.mockClear();
    toastMock.dismiss.mockClear();
  });
  afterEach(() => vi.useRealTimers());

  const user = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

  it("Loại: ẩn ngay, gửi đúng một request sau 5 giây", async () => {
    const { patches } = setup();
    await user().click(await screen.findByRole("button", { name: "Loại" }));
    expect(screen.queryByText("Đề bài câu q1 đủ dài")).not.toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(4900));
    expect(patches).toHaveLength(0);
    await act(() => vi.advanceTimersByTimeAsync(200));
    await waitFor(() => expect(patches).toEqual([{ id: "q1", body: { action: "reject" } }]));
  });

  it("Hoàn tác trong 5 giây: không gửi gì và câu hiện lại", async () => {
    const { patches } = setup();
    await user().click(await screen.findByRole("button", { name: "Loại" }));
    const opts = toastMock.mock.calls[0][1] as { action: { onClick: () => void } };
    act(() => opts.action.onClick());
    expect(screen.getByText("Đề bài câu q1 đủ dài")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(patches).toHaveLength(0);
  });

  it("rời trang khi đang chờ: gửi ngay một lần, không gửi lại khi hết giờ", async () => {
    const { patches, view } = setup();
    await user().click(await screen.findByRole("button", { name: "Loại" }));
    view.unmount();
    await waitFor(() => expect(patches).toHaveLength(1));
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(patches).toHaveLength(1);
  });

  it("rời trang sau khi đã gửi: không gửi lần hai", async () => {
    const { patches, view } = setup();
    await user().click(await screen.findByRole("button", { name: "Loại" }));
    await act(() => vi.advanceTimersByTimeAsync(5100));
    await waitFor(() => expect(patches).toHaveLength(1));
    view.unmount();
    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(patches).toHaveLength(1);
  });

  it("job sinh câu xong thì tải lại danh sách và báo số câu chờ duyệt", async () => {
    const { setItems, setJobStatus } = setup([]);
    await user().click(await screen.findByRole("button", { name: /Sinh câu hỏi bằng AI/ }));
    expect(await screen.findByText(/AI đang soạn/)).toBeInTheDocument();
    setItems([question("g1"), question("g2")]);
    setJobStatus("done");
    await act(() => vi.advanceTimersByTimeAsync(2100));
    expect(await screen.findByText("Đề bài câu g1 đủ dài")).toBeInTheDocument();
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith("AI đã soạn xong. Có 2 câu chờ duyệt."));
  });

  const err422 = (msg: string, type: string, loc: (string | number)[]) => () =>
    HttpResponse.json(
      { error: { code: "VALIDATION_ERROR", message: "Câu hỏi không hợp lệ", details: { errors: [{ loc, msg, type }] } } },
      { status: 422 },
    );

  async function editAndSave() {
    await user().click(await screen.findByRole("button", { name: "Sửa" }));
    await user().type(screen.getByLabelText("Lựa chọn B"), " sửa");
    await user().click(screen.getByRole("button", { name: "Lưu và duyệt" }));
  }

  it("422 khi sửa: hiện lỗi bằng tiếng Việt ngay trong form", async () => {
    const { setPatchReply, patches } = setup();
    setPatchReply(err422("String should have at least 10 characters", "string_too_short", ["stem"]));
    await editAndSave();
    expect(await screen.findByRole("alert")).toHaveTextContent("Câu hỏi không hợp lệ: Đề bài phải có ít nhất 10 ký tự");
    expect(patches[0].body.action).toBe("edit");
    expect(screen.getByRole("button", { name: "Lưu và duyệt" })).toBeInTheDocument();
  });

  it("422 từ luật câu hỏi: bỏ tiền tố 'Value error, '", async () => {
    const { setPatchReply } = setup();
    setPatchReply(err422("Value error, Có lựa chọn trùng nhau", "value_error", []));
    await editAndSave();
    expect(await screen.findByRole("alert")).toHaveTextContent(/^Câu hỏi không hợp lệ: Có lựa chọn trùng nhau$/);
  });

  it("lưu form sửa mà không đổi gì thì gửi approve, không gửi edit", async () => {
    const { patches } = setup();
    await user().click(await screen.findByRole("button", { name: "Sửa" }));
    await user().click(screen.getByRole("button", { name: "Lưu và duyệt" }));
    await waitFor(() => expect(patches).toEqual([{ id: "q1", body: { action: "approve" } }]));
  });

  it("Hoàn tác sau khi đã gửi loại: không hiện lại câu, báo không hoàn tác được; toast được đóng khi gửi", async () => {
    const { patches } = setup();
    await user().click(await screen.findByRole("button", { name: "Loại" }));
    const [, opts] = toastMock.mock.calls[0] as [string, { id: string; action: { onClick: () => void } }];
    await act(() => vi.advanceTimersByTimeAsync(5100));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(toastMock.dismiss).toHaveBeenCalledWith(opts.id);
    act(() => opts.action.onClick());
    expect(toastMock).toHaveBeenLastCalledWith("Đã gửi yêu cầu loại, không hoàn tác được nữa");
    expect(screen.queryByText("Đề bài câu q1 đủ dài")).not.toBeInTheDocument();
  });

  it("rời trang khi đang chờ loại: đóng toast, và báo lỗi nếu request thất bại", async () => {
    const { setPatchReply, view } = setup();
    setPatchReply(() => HttpResponse.json({ error: { code: "CONFLICT", message: "Câu hỏi đang nằm trong quiz" } }, { status: 409 }));
    await user().click(await screen.findByRole("button", { name: "Loại" }));
    const [, opts] = toastMock.mock.calls[0] as [string, { id: string }];
    view.unmount();
    expect(toastMock.dismiss).toHaveBeenCalledWith(opts.id);
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith("Câu hỏi đang nằm trong quiz"));
  });

  it("409 khi duyệt: báo lỗi bằng toast", async () => {
    const { setPatchReply } = setup();
    setPatchReply(() =>
      HttpResponse.json({ error: { code: "CONFLICT", message: "Câu hỏi đang nằm trong quiz đã xuất bản" } }, { status: 409 }),
    );
    const card = (await screen.findByText("Đề bài câu q1 đủ dài")).closest("article")!;
    await user().click(within(card as HTMLElement).getByRole("button", { name: "Duyệt" }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith("Câu hỏi đang nằm trong quiz đã xuất bản"));
  });
});
