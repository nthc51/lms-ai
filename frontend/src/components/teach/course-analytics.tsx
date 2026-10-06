"use client";

import { ArrowLeft, BarChart3 } from "lucide-react";
import Link from "next/link";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { Badge, Skeleton } from "@/components/ui/misc";
import { useCourse } from "@/lib/queries";
import { useCourseAnalytics } from "@/lib/quiz/queries";

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Bảng điều khiển của giảng viên (A8). Số liệu ít, đọc nhanh: thẻ số lớn cho con số chính, bảng có thanh
 * ngang cho tỉ lệ hoàn thành / tỉ lệ đạt (một màu, giá trị luôn in bằng chữ nên không phụ thuộc màu).
 */
export function CourseAnalyticsView({ slug }: { slug: string }) {
  const course = useCourse(slug);
  const stats = useCourseAnalytics(course.data?.id);

  return (
    <>
      <Link href={`/teach/${slug}`} className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {course.data?.title ?? "Khóa học"}
      </Link>
      <PageHeader title="Thống kê khóa học" />
      {course.isError || stats.isError ? (
        <ErrorState error={course.error ?? stats.error} onRetry={() => (course.refetch(), stats.refetch())} />
      ) : !stats.data ? (
        <div className="space-y-4" aria-busy="true" aria-label="Đang tải thống kê">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-60" />
        </div>
      ) : stats.data.enrollments === 0 ? (
        <EmptyState icon={BarChart3} title="Chưa có học viên nào đăng ký khóa này, nên chưa có số liệu." />
      ) : (
        <div className="space-y-10">
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Học viên đăng ký" value={stats.data.enrollments} />
            <Tile
              label="Hoàn thành khóa"
              value={stats.data.completed_enrollments}
              note={pct(stats.data.completed_enrollments / stats.data.enrollments)}
            />
            <Tile label="Câu hỏi gửi AI Tutor" value={stats.data.tutor.questions} note={`${stats.data.tutor.sessions} phiên`} />
            <Tile
              label="AI từ chối trả lời"
              value={stats.data.tutor.refused_answers}
              note={stats.data.tutor.questions ? pct(stats.data.tutor.refused_answers / stats.data.tutor.questions) : undefined}
            />
          </dl>

          <section aria-labelledby="lesson-stats">
            <h2 id="lesson-stats" className="mb-3 text-lg font-semibold">
              Tỉ lệ hoàn thành từng bài
            </h2>
            <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng tỉ lệ hoàn thành từng bài">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Bài học</th>
                    <th className="px-4 py-2 font-medium">Hoàn thành</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.data.lessons.map((l) => (
                    <tr key={l.lesson_id} className="border-b last:border-b-0">
                      <td className="px-4 py-2.5">
                        <span className="block">{l.title}</span>
                        <span className="text-xs text-muted-foreground">{l.section_title}</span>
                      </td>
                      <td className="w-1/2 px-4 py-2.5">
                        <Meter value={l.completion_rate} label={`${l.done_count}/${stats.data.enrollments} · ${pct(l.completion_rate)}`} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="quiz-stats">
            <h2 id="quiz-stats" className="mb-3 text-lg font-semibold">
              Quiz
            </h2>
            {stats.data.quizzes.length === 0 ? (
              <p className="text-sm text-muted-foreground">Khóa chưa có quiz nào.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng thống kê quiz">
                <table className="w-full min-w-[560px] text-sm">
                  <thead className="border-b text-left text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 font-medium">Quiz</th>
                      <th className="px-4 py-2 font-medium">Bài nộp</th>
                      <th className="px-4 py-2 font-medium">Học viên</th>
                      <th className="px-4 py-2 font-medium">Điểm TB</th>
                      <th className="px-4 py-2 font-medium">Tỉ lệ đạt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.data.quizzes.map((q) => (
                      <tr key={q.quiz_id} className="border-b last:border-b-0">
                        <td className="px-4 py-2.5">
                          {q.title} {q.status === "draft" ? <Badge className="ml-1">Nháp</Badge> : null}
                        </td>
                        <td className="px-4 py-2.5 tabular-nums">{q.attempts}</td>
                        <td className="px-4 py-2.5 tabular-nums">{q.students}</td>
                        <td className="px-4 py-2.5 tabular-nums">{q.avg_score == null ? "—" : `${q.avg_score.toFixed(1)}%`}</td>
                        <td className="w-1/3 px-4 py-2.5">
                          {q.pass_rate == null ? "—" : <Meter value={q.pass_rate} label={pct(q.pass_rate)} />}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function Tile({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="rounded-lg border bg-surface p-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="mt-1 flex items-baseline gap-2">
        <span className="text-3xl font-semibold tabular-nums">{value}</span>
        {note ? <span className="text-sm text-muted-foreground">{note}</span> : null}
      </dd>
    </div>
  );
}

/** Thanh ngang một màu; con số luôn in kèm nên không phụ thuộc màu (dataviz: text dùng màu chữ, không dùng màu thanh). */
function Meter({ value, label }: { value: number; label: string }) {
  const v = Math.min(1, Math.max(0, value));
  return (
    <div className="flex items-center gap-3" title={label}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className="h-full rounded-full bg-accent" style={{ width: `${v * 100}%` }} />
      </div>
      <span className="w-24 shrink-0 text-right tabular-nums">{label}</span>
    </div>
  );
}
