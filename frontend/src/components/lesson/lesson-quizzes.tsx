"use client";

import { ClipboardCheck, Play, RotateCcw } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { lastAttempt } from "@/lib/quiz/attempt-store";
import { useLessonQuizzes } from "@/lib/quiz/queries";
import { formatScore } from "@/components/quiz/quiz-result";

/**
 * Quiz của bài, hiện dưới nội dung bài học. Học viên chỉ thấy quiz đã xuất bản (backend lọc).
 * Lỗi tải không chặn trang học: chỉ hiện một dòng nhỏ.
 */
export function LessonQuizzes({ slug, lessonId, isStudent }: { slug: string; lessonId: string; isStudent: boolean }) {
  const quizzes = useLessonQuizzes(lessonId);
  if (quizzes.isPending) return <Skeleton className="mt-10 h-20 w-full" />;
  if (quizzes.isError) return <p className="mt-10 text-sm text-muted-foreground">Không tải được danh sách quiz của bài.</p>;
  const items = quizzes.data.items;
  if (!items.length) return null;

  return (
    <section aria-labelledby="lesson-quizzes" className="mt-10">
      <h2 id="lesson-quizzes" className="flex items-center gap-2 text-lg font-semibold">
        <ClipboardCheck className="size-5 text-accent" aria-hidden /> Kiểm tra nhanh
      </h2>
      <ul className="mt-3 space-y-3">
        {items.map((q) => {
          const base = `/learn/${slug}/${lessonId}/quiz/${q.id}`;
          const last = isStudent ? lastAttempt.get(q.id) : null;
          const used = q.attempts_used ?? 0;
          const left = q.max_attempts - used;
          const inProgress = last?.status === "in_progress";
          return (
            <li key={q.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{q.title}</p>
                <p className="text-sm text-muted-foreground">
                  {q.question_count} câu · đạt từ {q.pass_score}%
                  {isStudent ? ` · đã làm ${used}/${q.max_attempts} lượt` : ""}
                </p>
              </div>
              {!isStudent ? (
                <Badge tone={q.status === "published" ? "success" : "neutral"}>
                  {q.status === "published" ? "Đã xuất bản" : "Nháp"}
                </Badge>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {last && last.status !== "in_progress" && last.score != null ? (
                    <Button asChild variant="link">
                      <Link href={`${base}/result/${last.attemptId}`}>Điểm gần nhất {formatScore(last.score)}</Link>
                    </Button>
                  ) : null}
                  {inProgress || left > 0 ? (
                    <Button asChild variant="outline">
                      <Link href={base}>
                        {inProgress ? <Play /> : used > 0 ? <RotateCcw /> : <Play />}
                        {inProgress ? "Làm tiếp" : used > 0 ? "Làm lại" : "Làm bài"}
                      </Link>
                    </Button>
                  ) : (
                    <span className="text-sm text-muted-foreground">Đã hết lượt</span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
