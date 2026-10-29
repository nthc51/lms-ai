"use client";

import { NotebookPen } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { type Assignment, useLessonAssignments } from "@/lib/assignments";
import { formatDateTime } from "@/lib/format";

/** Trạng thái theo góc nhìn học viên: không lộ việc AI đã chấm hay chưa, chỉ "đã nộp" / "đã có điểm". */
function studentState(a: Assignment): { label: string; tone: "neutral" | "success" | "accent"; action: string } {
  const mine = a.my_submission;
  if (!mine) return { label: "Chưa nộp", tone: "neutral", action: "Làm bài" };
  if (mine.status === "graded") return { label: `${mine.final_total}/${a.max_total} điểm`, tone: "success", action: "Xem điểm" };
  return { label: "Đã nộp, chờ chấm", tone: "accent", action: "Xem bài nộp" };
}

/** Bài tập của bài (B5), hiện dưới quiz trong trang học. Không có bài tập nào thì ẩn cả mục. */
export function LessonAssignments({ slug, lessonId, isStudent }: { slug: string; lessonId: string; isStudent: boolean }) {
  const list = useLessonAssignments(lessonId);
  if (list.isPending) return <Skeleton className="mt-10 h-20 w-full" />;
  if (list.isError) return <p className="mt-10 text-sm text-muted-foreground">Không tải được danh sách bài tập của bài.</p>;
  const items = list.data.items;
  if (!items.length) return null;

  return (
    <section aria-labelledby="lesson-assignments" className="mt-10">
      <h2 id="lesson-assignments" className="flex items-center gap-2 text-lg font-semibold">
        <NotebookPen className="size-5 text-accent" aria-hidden /> Bài tập
      </h2>
      <ul className="mt-3 space-y-3">
        {items.map((a) => {
          const state = isStudent ? studentState(a) : null;
          return (
            <li key={a.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{a.title}</p>
                <p className="text-sm text-muted-foreground">
                  {a.rubric.length} tiêu chí · {a.max_total} điểm · {a.due_at ? `hạn ${formatDateTime(a.due_at)}` : "không có hạn nộp"}
                </p>
              </div>
              {state ? (
                <>
                  <Badge tone={state.tone}>{state.label}</Badge>
                  <Button asChild variant="outline">
                    <Link href={`/assignments/${a.id}`}>{state.action}</Link>
                  </Button>
                </>
              ) : (
                <>
                  <Badge tone={a.status === "published" ? "success" : "neutral"}>{a.status === "published" ? "Đã xuất bản" : "Nháp"}</Badge>
                  <Button asChild variant="outline">
                    <Link href={`/teach/${slug}/lessons/${lessonId}/assignments/${a.id}`}>Bài nộp ({a.submission_count ?? 0})</Link>
                  </Button>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
