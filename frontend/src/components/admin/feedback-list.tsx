"use client";

import { ThumbsDown } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/app/states";
import { Badge } from "@/components/ui/misc";
import { fmtDateTime, type TutorFeedback } from "@/lib/admin-queries";

/**
 * Câu trả lời AI Tutor bị học viên bấm 👎: câu hỏi, câu trả lời, nơi hỏi. Dùng chung cho admin (mọi khóa,
 * có tên học viên) và giảng viên (một khóa, không có tên để học viên dám bấm).
 */
export function FeedbackList({ items, showCourse }: { items: TutorFeedback[]; showCourse: boolean }) {
  if (items.length === 0) return <EmptyState icon={ThumbsDown} title="Chưa có câu trả lời nào bị chê." />;
  return (
    <ol className="space-y-3">
      {items.map((f) => (
        <li key={f.message_id} className="rounded-lg border bg-surface p-4">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            {showCourse ? (
              <Link href={`/courses/${f.course_slug}`} className="font-medium text-primary hover:underline">
                {f.course_title}
              </Link>
            ) : null}
            {f.lesson_title ? <span>· {f.lesson_title}</span> : <span>· Hỏi trên toàn khóa</span>}
            {f.student_name ? <span>· {f.student_name}</span> : null}
            <time dateTime={f.created_at}>· {fmtDateTime(f.created_at)}</time>
            {f.refused ? <Badge>AI đã từ chối trả lời</Badge> : null}
          </div>
          <p className="mt-2 text-sm">
            <span className="font-medium">Hỏi:</span> {f.question ?? "(không còn câu hỏi)"}
          </p>
          <details className="mt-1 text-sm">
            <summary className="cursor-pointer text-muted-foreground">Câu trả lời của AI</summary>
            <p className="mt-1 whitespace-pre-wrap">{f.answer}</p>
          </details>
        </li>
      ))}
    </ol>
  );
}
