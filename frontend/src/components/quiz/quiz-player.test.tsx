import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { QuizPlayer } from "./quiz-player";

const replace = vi.fn();
const toastInfo = vi.fn();
const toastError = vi.fn();
const hook = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { info: (m: string) => toastInfo(m), error: (m: string) => toastError(m) } }));
vi.mock("@/lib/quiz/queries", () => ({ useQuiz: () => ({ data: { title: "Quiz thử" } }) }));
vi.mock("@/lib/quiz/use-quiz-attempt", () => ({ useQuizAttempt: () => hook.current }));

const attemptData = {
  id: "a1",
  deadline_at: null,
  answers: {},
  questions: [
    {
      id: "q1",
      stem: "Câu một?",
      options: [
        { id: "A", text: "Đáp án A" },
        { id: "B", text: "Đáp án B" },
      ],
    },
  ],
};

function setHook(over: Record<string, unknown> = {}) {
  hook.current = {
    attempt: { isError: false, isPending: false, data: attemptData },
    attemptId: "a1",
    closed: false,
    answers: { q1: "A" },
    saveStates: { q1: "error" },
    select: vi.fn(),
    submit: vi.fn(),
    ...over,
  };
}

const RESULT_URL = "/learn/toan/l1/quiz/qz1/result/a1";
const renderPlayer = () => render(<QuizPlayer slug="toan" lessonId="l1" quizId="qz1" />);

describe("QuizPlayer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setHook();
  });

  it("closed=true: chuyển sang trang kết quả đúng một lần, báo toast, không hiện 'sẽ gửi khi nộp'", async () => {
    setHook({ closed: true });
    const { rerender } = renderPlayer();
    await waitFor(() => expect(replace).toHaveBeenCalledTimes(1));
    expect(replace).toHaveBeenCalledWith(RESULT_URL);
    expect(toastInfo).toHaveBeenCalledWith(expect.stringContaining("đã được nộp ở nơi khác"));
    expect(screen.getByText("Bài đã nộp")).toBeInTheDocument();
    expect(screen.queryByText(/sẽ gửi khi nộp/)).not.toBeInTheDocument();
    rerender(<QuizPlayer slug="toan" lessonId="l1" quizId="qz1" />);
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it("nộp bị ATTEMPT_CLOSED: chuyển sang kết quả đúng một lần", async () => {
    const submit = vi.fn().mockRejectedValue(new ApiError(409, "ATTEMPT_CLOSED", "đã nộp"));
    setHook({ submit });
    renderPlayer();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Nộp bài" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Nộp bài" }));
    await waitFor(() => expect(replace).toHaveBeenCalledTimes(1));
    expect(replace).toHaveBeenCalledWith(RESULT_URL);
    expect(toastInfo).toHaveBeenCalledTimes(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("đang nộp: vô hiệu các đáp án và nút Nộp bài", async () => {
    const submit = vi.fn(() => new Promise(() => {})); // không bao giờ xong
    setHook({ submit });
    renderPlayer();
    const user = userEvent.setup();
    expect(screen.getByRole("radio", { name: /Đáp án A/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Nộp bài" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Nộp bài" }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    for (const r of screen.getAllByRole("radio", { hidden: true })) expect(r).toBeDisabled();
    expect(replace).not.toHaveBeenCalled();
  });
});
