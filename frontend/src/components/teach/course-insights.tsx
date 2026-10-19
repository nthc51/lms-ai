"use client";

import { CircleAlert } from "lucide-react";
import Link from "next/link";
import { Skeleton } from "@/components/ui/misc";
import { Meter } from "@/components/teach/meter";
import { timeAgo } from "@/lib/format";
import { useCourseInsights } from "@/lib/quiz/queries";

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Phân tích lớp học (B7) dưới bảng thống kê: ba danh sách ngắn giúp giảng viên biết nên sửa gì và nhắc ai.
 * Mỗi dòng dẫn tới đúng chỗ cần sửa (ngân hàng câu hỏi của bài, trang bài học).
 */
export function CourseInsightsSection({ slug, courseId }: { slug: string; courseId: string }) {
  const insights = useCourseInsights(courseId);
  if (insights.isPending) return <Skeleton className="mt-10 h-60" aria-label="Đang tải phân tích lớp học" />;
  if (insights.isError) return null; // bảng thống kê phía trên đã báo lỗi tải nếu có
  const { hard_questions, weak_lessons, students_at_risk, min_answers } = insights.data;

  return (
    <div className="mt-10 space-y-10">
      <section aria-labelledby="hard-q">
        <h2 id="hard-q" className="mb-1 text-lg font-semibold">
          Câu hỏi học viên hay làm sai
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Chỉ xếp hạng câu có từ {min_answers} lượt trả lời. Tỉ lệ sai cao thường do đề chưa rõ, đáp án sai hoặc tài liệu chưa nói kỹ.
        </p>
        {hard_questions.length === 0 ? (
          <p className="bg-surface p-4 text-sm text-muted-foreground">Chưa đủ lượt làm bài để xếp hạng.</p>
        ) : (
          <ol className="flex flex-col gap-1.5">
            {hard_questions.map((q) => (
              <li key={q.question_id}>
                <Link
                  href={`/teach/${slug}/lessons/${q.lesson_id}/questions`}
                  className="group grid gap-3 bg-surface p-4 transition-colors duration-150 hover:bg-field-3 md:grid-cols-[minmax(0,1fr)_220px] md:gap-6"
                >
                  <span className="min-w-0">
                    <span className="line-clamp-2 block font-medium">{q.stem}</span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      {q.lesson_title}
                      {q.source_page != null ? ` · tài liệu trang ${q.source_page}` : ""} · đáp án đúng {q.correct_option}
                      {q.top_wrong ? `, hay chọn nhầm ${q.top_wrong.id} (${q.top_wrong.count} lượt)` : ""}
                    </span>
                  </span>
                  <span className="flex flex-col justify-center gap-1 text-sm">
                    <Meter value={q.wrong_rate} label={`${pct(q.wrong_rate)} sai`} />
                    <span className="text-right text-xs text-muted-foreground tabular-nums">
                      {q.wrong}/{q.answers} lượt
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="weak-l">
        <h2 id="weak-l" className="mb-1 text-lg font-semibold">
          Bài học cần xem lại
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">Xếp theo điểm quiz trung bình thấp nhất, rồi theo số câu học viên hỏi AI Tutor.</p>
        {weak_lessons.length === 0 ? (
          <p className="bg-surface p-4 text-sm text-muted-foreground">Chưa có bài nào có số liệu.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng bài học cần xem lại">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="border-b text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Bài học</th>
                  <th className="px-4 py-2 font-medium">Điểm quiz TB</th>
                  <th className="px-4 py-2 font-medium">Bài nộp</th>
                  <th className="px-4 py-2 font-medium">Câu hỏi AI Tutor</th>
                </tr>
              </thead>
              <tbody>
                {weak_lessons.map((l) => (
                  <tr key={l.lesson_id} className="border-b last:border-b-0">
                    <td className="px-4 py-2.5">
                      <Link href={`/teach/${slug}/lessons/${l.lesson_id}`} className="block font-medium hover:underline">
                        {l.title}
                      </Link>
                      <span className="text-xs text-muted-foreground">{l.section_title}</span>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums">{l.avg_score == null ? "—" : `${l.avg_score.toFixed(1)}%`}</td>
                    <td className="px-4 py-2.5 tabular-nums">{l.attempts}</td>
                    <td className="px-4 py-2.5 tabular-nums">{l.tutor_questions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="at-risk">
        <h2 id="at-risk" className="mb-1 text-lg font-semibold">
          Học viên cần để ý ({students_at_risk.length})
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Chưa xong khóa và điểm quiz trung bình dưới 50% hoặc 7 ngày không học. Ai lâu không học nhất đứng đầu.
        </p>
        {students_at_risk.length === 0 ? (
          <p className="bg-surface p-4 text-sm text-muted-foreground">Không có học viên nào cần để ý lúc này.</p>
        ) : (
          <ul className="grid gap-1.5 md:grid-cols-2">
            {students_at_risk.map((s) => (
              <li key={s.user_id} className="flex flex-col gap-2 bg-surface p-4">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="font-semibold">{s.full_name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">học lần cuối {timeAgo(s.last_active_at)}</span>
                </span>
                <Meter value={s.progress_pct / 100} label={`${s.progress_pct}% khóa`} />
                <ul className="flex flex-wrap gap-1.5">
                  {s.reasons.map((r) => (
                    <li key={r} className="inline-flex items-center gap-1 bg-field-2 px-2 py-0.5 text-xs font-semibold text-foreground">
                      <CircleAlert className="size-3.5" aria-hidden /> {r}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
