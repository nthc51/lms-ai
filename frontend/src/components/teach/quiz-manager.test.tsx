import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { quizKeys } from "@/lib/quiz/queries";
import { api as url, server } from "@/test/msw";
import { QuizManager } from "./quiz-manager";

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

const quiz = (id: string, status: "draft" | "published", question_count: number) => ({
  id,
  lesson_id: "l1",
  title: `Quiz ${id}`,
  status,
  max_attempts: 3,
  pass_score: 50,
  question_count,
  attempts_used: null,
});

function setup(items: ReturnType<typeof quiz>[]) {
  server.use(
    http.get(url("/quizzes"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 50 })),
    http.get(url("/quizzes/:id"), ({ params }) => {
      return HttpResponse.json({ ...items.find((q) => q.id === params.id), questions: [] });
    }),
    http.post(url("/quizzes/:id/publish"), ({ params }) => HttpResponse.json(quiz(params.id as string, "published", 2))),
    http.get(url("/lessons/l1/questions"), () => HttpResponse.json({ items: [], total: 0, page: 1, size: 100 })),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <QuizManager lessonId="l1" />
    </QueryClientProvider>,
  );
  return { qc };
}

describe("QuizManager", () => {
  beforeEach(() => toastMock.success.mockClear());

  it("published quiz has no actions menu, draft offers 'Xóa quiz'", async () => {
    const user = userEvent.setup();
    setup([quiz("pub", "published", 2), quiz("dra", "draft", 2)]);
    await screen.findByText("Quiz pub");
    expect(screen.queryByRole("button", { name: "Thao tác với quiz Quiz pub" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Thao tác với quiz Quiz dra" }));
    expect(await screen.findByRole("menuitem", { name: /Xóa quiz/ })).toBeInTheDocument();
  });

  it("draft with 0 questions: publish disabled with a described hint; with questions: enabled", async () => {
    setup([quiz("empty", "draft", 0), quiz("full", "draft", 2)]);
    await screen.findByText("Quiz empty");
    const buttons = screen.getAllByRole("button", { name: /Xuất bản/ });
    expect(buttons[0]).toBeDisabled();
    expect(buttons[0]).toHaveAccessibleDescription("Chọn ít nhất 1 câu hỏi để xuất bản");
    expect(buttons[1]).toBeEnabled();
    expect(buttons[1]).not.toHaveAttribute("aria-describedby");
    expect(screen.getAllByText("Chọn ít nhất 1 câu hỏi để xuất bản")).toHaveLength(1);
  });

  it("publishing invalidates the cached quiz detail", async () => {
    const user = userEvent.setup();
    const { qc } = setup([quiz("full", "draft", 2)]);
    await screen.findByText("Quiz full");
    await qc.fetchQuery({ queryKey: quizKeys.quiz("full"), queryFn: () => fetch(url("/quizzes/full")).then((r) => r.json()) });
    expect(qc.getQueryState(quizKeys.quiz("full"))?.isInvalidated).toBe(false);
    await user.click(screen.getByRole("button", { name: /Xuất bản/ }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Xuất bản" }));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith("Đã xuất bản quiz"));
    expect(qc.getQueryState(quizKeys.quiz("full"))?.isInvalidated).toBe(true);
  });

  it("edit dialog does not allow saving when the quiz detail fails to load", async () => {
    const user = userEvent.setup();
    let patched = false;
    setup([quiz("dra", "draft", 2)]);
    server.use(
      http.get(url("/quizzes/dra"), () => HttpResponse.json({ error: { code: "INTERNAL", message: "Lỗi máy chủ" } }, { status: 500 })),
      http.patch(url("/quizzes/dra"), () => {
        patched = true;
        return HttpResponse.json(quiz("dra", "draft", 0));
      }),
    );
    await screen.findByText("Quiz dra");
    await user.click(screen.getByRole("button", { name: "Sửa" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
    const save = within(dialog).getByRole("button", { name: "Lưu quiz" });
    expect(save).toBeDisabled();
    await user.click(save);
    expect(patched).toBe(false);
  });
});
