"use client";

import { ArrowLeft, Check, ChevronLeft, ChevronRight, CloudOff, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { BreakReminder } from "@/components/lesson/break-reminder";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Progress, Skeleton } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";
import type { SaveState } from "@/lib/quiz/answer-saver";
import { lastAttempt } from "@/lib/quiz/attempt-store";
import { useQuiz } from "@/lib/quiz/queries";
import { useQuizAttempt } from "@/lib/quiz/use-quiz-attempt";
import { cn } from "@/lib/utils";

/**
 * Làm quiz (design-system §5.3, phần Quiz): từng câu một, chọn đáp án bằng thẻ cả dòng (radio, ≥ 48px),
 * tự lưu và báo "Đã lưu" cạnh câu, Câu trước/Câu sau, lưới câu để nhảy nhanh, Nộp bài có xác nhận
 * khi còn câu chưa trả lời.
 */
export function QuizPlayer({ slug, lessonId, quizId }: { slug: string; lessonId: string; quizId: string }) {
  const router = useRouter();
  const quiz = useQuiz(quizId);
  const { attempt, attemptId, closed, answers, saveStates, select, submit } = useQuizAttempt(quizId);
  const [index, setIndex] = React.useState(0);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const lessonHref = `/learn/${slug}/${lessonId}`;
  // chỉ chuyển sang trang kết quả một lần (nộp xong, bài đã đóng, bấm đúp)
  const navigated = React.useRef(false);

  const goToResult = React.useCallback(
    (id: string, notice?: string) => {
      if (navigated.current) return;
      navigated.current = true;
      if (notice) toast.info(notice);
      router.replace(`${lessonHref}/quiz/${quizId}/result/${id}`);
    },
    [router, lessonHref, quizId],
  );

  React.useEffect(() => {
    if (closed && attemptId) {
      goToResult(attemptId, "Bài làm này đã được nộp ở nơi khác. Đang mở kết quả…");
    }
  }, [closed, attemptId, goToResult]);

  if (attempt.isError) {
    const err = attempt.error;
    if (err instanceof ApiError && err.code === "QUIZ_ATTEMPT_LIMIT") {
      const last = lastAttempt.get(quizId);
      return (
        <Shell title={quiz.data?.title} lessonHref={lessonHref}>
          <div className="mx-auto max-w-md rounded-lg border p-6 text-center">
            <p className="font-medium">Bạn đã dùng hết số lần làm quiz này.</p>
            <div className="mt-4 flex flex-col justify-center gap-2 sm:flex-row">
              {last && last.status !== "in_progress" ? (
                <Button asChild>
                  <Link href={`${lessonHref}/quiz/${quizId}/result/${last.attemptId}`}>Xem kết quả gần nhất</Link>
                </Button>
              ) : null}
              <Button asChild variant="outline">
                <Link href={lessonHref}>Về bài học</Link>
              </Button>
            </div>
          </div>
        </Shell>
      );
    }
    return (
      <Shell title={quiz.data?.title} lessonHref={lessonHref}>
        <ErrorState error={err} onRetry={() => attempt.refetch()} />
      </Shell>
    );
  }

  if (attempt.isPending)
    return (
      <Shell title={quiz.data?.title} lessonHref={lessonHref}>
        <div className="space-y-4" aria-busy="true" aria-label="Đang mở bài làm">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-24 w-full" />
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      </Shell>
    );

  const questions = attempt.data.questions;
  const q = questions[Math.min(index, questions.length - 1)];
  const answeredCount = questions.filter((x) => answers[x.id]).length;
  const unanswered = questions.length - answeredCount;
  const isLast = index === questions.length - 1;
  // đang nộp hoặc bài đã đóng: không cho đổi đáp án (một lựa chọn lúc nộp sẽ bị rơi khỏi final_answers)
  const locked = submitting || closed;

  async function doSubmit() {
    if (navigated.current) return;
    setSubmitting(true);
    try {
      const result = await submit();
      goToResult(result.attempt_id);
    } catch (err) {
      if (err instanceof ApiError && err.code === "ATTEMPT_CLOSED" && attemptId) {
        setConfirmOpen(false);
        goToResult(attemptId, "Bài làm này đã được nộp ở nơi khác. Đang mở kết quả…");
        return;
      }
      toast.error(errorMessage(err));
      setSubmitting(false);
      throw err; // giữ hộp xác nhận mở
    }
  }

  return (
    <Shell title={quiz.data?.title} lessonHref={lessonHref}>
      <div className="grid gap-8 lg:grid-cols-[1fr_220px]">
        <section aria-labelledby="q-stem">
          <div className="mb-4 flex items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>
              Câu {index + 1}/{questions.length}
            </span>
            <SaveBadge state={saveStates[q.id]} closed={closed} />
          </div>
          <Progress value={(answeredCount / questions.length) * 100} label={`Đã trả lời ${answeredCount}/${questions.length} câu`} />

          <fieldset className="mt-6">
            <legend id="q-stem" className="reader mb-4 text-lg font-medium [--reader-size:18px]">
              {q.stem}
            </legend>
            <div className="space-y-3">
              {q.options.map((o) => {
                const checked = answers[q.id] === o.id;
                return (
                  <label
                    key={o.id}
                    className={cn(
                      "flex min-h-12 cursor-pointer items-start gap-3 rounded-lg border bg-surface px-4 py-3 transition-colors duration-150 hover:border-primary/60",
                      "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
                      checked && "border-primary bg-primary/10",
                      locked && "cursor-not-allowed opacity-70",
                    )}
                  >
                    <input
                      type="radio"
                      name={`q-${q.id}`}
                      value={o.id}
                      checked={checked}
                      disabled={locked}
                      onChange={() => select(q.id, o.id)}
                      className="sr-only"
                    />
                    <span
                      aria-hidden
                      className={cn(
                        "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border text-xs font-semibold",
                        checked && "border-primary bg-primary text-primary-foreground",
                      )}
                    >
                      {o.id}
                    </span>
                    <span className="reader [--reader-size:16px]">{o.text}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
            <Button variant="outline" disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>
              <ChevronLeft /> Câu trước
            </Button>
            {isLast ? (
              <Button size="lg" disabled={locked} onClick={() => setConfirmOpen(true)}>
                <Send /> Nộp bài
              </Button>
            ) : (
              <Button variant="outline" onClick={() => setIndex((i) => i + 1)}>
                Câu sau <ChevronRight />
              </Button>
            )}
          </div>
        </section>

        <aside aria-label="Danh sách câu hỏi">
          <p className="mb-2 text-sm text-muted-foreground">
            Đã trả lời {answeredCount}/{questions.length}
          </p>
          <ol className="grid grid-cols-6 gap-2 lg:grid-cols-5">
            {questions.map((x, i) => (
              <li key={x.id}>
                <button
                  type="button"
                  onClick={() => setIndex(i)}
                  aria-current={i === index ? "step" : undefined}
                  aria-label={`Câu ${i + 1}${answers[x.id] ? ", đã trả lời" : ", chưa trả lời"}`}
                  className={cn(
                    "grid size-11 place-items-center rounded-md border text-sm",
                    answers[x.id] && "border-primary/50 bg-primary/10",
                    i === index && "ring-2 ring-primary",
                  )}
                >
                  {i + 1}
                </button>
              </li>
            ))}
          </ol>
          {!isLast ? (
            <Button variant="outline" className="mt-4 w-full" disabled={locked} onClick={() => setConfirmOpen(true)}>
              <Send /> Nộp bài
            </Button>
          ) : null}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmOpen && !closed} // bài đã đóng thì hộp xác nhận tự đóng
        onOpenChange={setConfirmOpen}
        title="Nộp bài?"
        description={
          unanswered > 0
            ? `Còn ${unanswered} câu chưa trả lời. Câu chưa trả lời được tính là sai. Sau khi nộp không sửa được nữa.`
            : "Bạn đã trả lời tất cả các câu. Sau khi nộp không sửa được nữa."
        }
        confirmLabel="Nộp bài"
        pendingLabel="Đang nộp…"
        onConfirm={doSubmit}
      />
      {/* quiz có giờ (tầng B1) thì không nhắc nghỉ giữa chừng */}
      <BreakReminder paused={!!attempt.data.deadline_at || submitting} />
    </Shell>
  );
}

function SaveBadge({ state, closed }: { state: SaveState | undefined; closed: boolean }) {
  // bài đã nộp ở nơi khác: không hiện "sẽ gửi khi nộp" hay trạng thái lưu nào nữa
  if (closed) return <span aria-live="polite">Bài đã nộp</span>;
  if (!state) return null;
  const map = {
    saving: { icon: <Loader2 className="size-3.5 animate-spin" aria-hidden />, text: "Đang lưu…", cls: "" },
    saved: { icon: <Check className="size-3.5" aria-hidden />, text: "Đã lưu", cls: "text-success" },
    error: { icon: <CloudOff className="size-3.5" aria-hidden />, text: "Chưa lưu được, sẽ gửi khi nộp", cls: "text-destructive" },
  }[state];
  return (
    <span aria-live="polite" className={cn("flex items-center gap-1", map.cls)}>
      {map.icon}
      {map.text}
    </span>
  );
}

function Shell({ title, lessonHref, children }: { title?: string; lessonHref: string; children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/95 px-2 backdrop-blur md:px-4">
        <Button asChild variant="ghost" size="icon" aria-label="Về bài học">
          <Link href={lessonHref}>
            <ArrowLeft />
          </Link>
        </Button>
        <h1 className="min-w-0 flex-1 truncate font-semibold">{title ?? "Quiz"}</h1>
      </header>
      <main id="main" className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 md:px-8">
        {children}
      </main>
    </div>
  );
}
