"use client";

import { ArrowLeft, CheckCircle2, CircleSlash, RotateCcw, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { useAttemptResult, useQuiz } from "@/lib/quiz/queries";
import type { AttemptResult } from "@/lib/quiz/types";
import { cn } from "@/lib/utils";

/**
 * Kết quả quiz: điểm, đạt/chưa đạt (icon + chữ, không chỉ màu), từng câu có đáp án đúng và giải thích.
 * Câu sai mở sẵn giải thích; có bộ lọc "Chỉ câu sai" cho buổi ôn dài.
 */
export function QuizResult({ slug, lessonId, quizId, attemptId }: { slug: string; lessonId: string; quizId: string; attemptId: string }) {
  const result = useAttemptResult(attemptId);
  const quiz = useQuiz(quizId);
  const [onlyWrong, setOnlyWrong] = React.useState(false);
  const lessonHref = `/learn/${slug}/${lessonId}`;

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/95 px-2 backdrop-blur md:px-4">
        <Button asChild variant="ghost" size="icon" aria-label="Về bài học">
          <Link href={lessonHref}>
            <ArrowLeft />
          </Link>
        </Button>
        <p className="min-w-0 flex-1 truncate font-semibold">{quiz.data?.title ?? "Kết quả quiz"}</p>
      </header>
      <main id="main" className="mx-auto w-full max-w-3xl px-4 pb-16 pt-6 md:px-8">
        {result.isPending ? (
          <div className="space-y-4" aria-busy="true" aria-label="Đang tải kết quả">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : result.isError ? (
          <ErrorState error={result.error} onRetry={() => result.refetch()} />
        ) : (
          <>
            <Summary r={result.data} />
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" checked={onlyWrong} onChange={(e) => setOnlyWrong(e.target.checked)} className="size-4 accent-[var(--primary)]" />
                Chỉ xem câu sai ({result.data.total - result.data.correct_count})
              </label>
              <div className="flex flex-col gap-2 sm:flex-row">
                {quiz.data && quiz.data.attempts_used != null && quiz.data.attempts_used < quiz.data.max_attempts ? (
                  <Button asChild variant="outline">
                    <Link href={`${lessonHref}/quiz/${quizId}`}>
                      <RotateCcw /> Làm lại ({quiz.data.max_attempts - quiz.data.attempts_used} lượt còn lại)
                    </Link>
                  </Button>
                ) : null}
                <Button asChild>
                  <Link href={lessonHref}>Về bài học</Link>
                </Button>
              </div>
            </div>
            <ol className="mt-6 space-y-4">
              {result.data.questions.map((q, i) =>
                onlyWrong && q.is_correct ? null : <ResultItem key={q.id} q={q} n={i + 1} />,
              )}
            </ol>
          </>
        )}
      </main>
    </div>
  );
}

function Summary({ r }: { r: AttemptResult }) {
  return (
    <section aria-labelledby="result-title" className="rounded-lg border bg-surface p-6">
      <h1 id="result-title" className="text-sm font-medium text-muted-foreground">
        Kết quả lần làm {r.attempt_no}
      </h1>
      <div className="mt-2 flex flex-wrap items-end gap-4">
        <p className="text-5xl font-semibold tabular-nums">{formatScore(r.score)}</p>
        <p className="pb-1 text-muted-foreground">
          {r.correct_count}/{r.total} câu đúng
        </p>
        <Badge tone={r.passed ? "success" : "destructive"} className="mb-1.5 text-sm">
          {r.passed ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
          {r.passed ? "Đạt" : "Chưa đạt"}
        </Badge>
      </div>
      {r.status === "timed_out" ? <p className="mt-2 text-sm text-muted-foreground">Bài được tự nộp khi hết giờ.</p> : null}
    </section>
  );
}

function ResultItem({ q, n }: { q: AttemptResult["questions"][number]; n: number }) {
  const unanswered = q.selected_option_id == null;
  return (
    <li className="rounded-lg border bg-surface p-4">
      <div className="flex items-start gap-2">
        {q.is_correct ? (
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-hidden />
        ) : unanswered ? (
          <CircleSlash className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <XCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted-foreground">
            Câu {n} · {q.is_correct ? "Đúng" : unanswered ? "Chưa trả lời" : "Sai"}
          </p>
          <p className="reader mt-1 font-medium [--reader-size:16px]">{q.stem}</p>
          <ul className="mt-3 space-y-1.5">
            {q.options.map((o) => {
              const correct = o.id === q.correct_option_id;
              const chosen = o.id === q.selected_option_id;
              return (
                <li
                  key={o.id}
                  className={cn(
                    "flex items-start gap-2 rounded-md border px-3 py-2 text-sm",
                    correct && "border-success/60 bg-success/10",
                    chosen && !correct && "border-destructive/60 bg-destructive/10",
                  )}
                >
                  <span className="font-semibold">{o.id}.</span>
                  <span className="flex-1">{o.text}</span>
                  {correct ? (
                    <span className="flex shrink-0 items-center gap-1 font-medium">
                      <CheckCircle2 className="size-4 text-success" aria-hidden /> Đáp án đúng
                    </span>
                  ) : null}
                  {chosen && !correct ? (
                    <span className="flex shrink-0 items-center gap-1 font-medium">
                      <XCircle className="size-4 text-destructive" aria-hidden /> Bạn chọn
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {q.explanation ? (
            <details className="mt-3" open={!q.is_correct}>
              <summary className="cursor-pointer text-sm font-medium text-primary underline-offset-4 hover:underline">
                Giải thích
              </summary>
              <p className="reader mt-2 text-muted-foreground [--reader-size:15px]">{q.explanation}</p>
            </details>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function formatScore(score: number) {
  return `${Number.isInteger(score) ? score : score.toFixed(1)}%`;
}
