"use client";

import { ArrowRight, BookMarked, PlayCircle } from "lucide-react";
import Link from "next/link";
import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
import { CourseCard } from "@/components/course/course-card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/misc";
import { useMyCourses } from "@/lib/queries";
import { lastLesson } from "@/lib/study/storage";
import { useMounted } from "@/lib/use-mounted";

/** Có bài mở gần nhất trên máy này → vào thẳng bài đó; không thì mở trang khóa. */
export function resumeHref(courseId: string, slug: string) {
  const last = lastLesson.get(courseId);
  return last ? `/learn/${slug}/${last}` : `/courses/${slug}`;
}

/**
 * Thẻ "Học tiếp" ở đầu trang chủ học viên: khóa chưa xong đầu tiên (theo thứ tự danh sách) mà máy này
 * còn nhớ bài đang học, bấm một lần là vào đúng bài. Chưa học bài nào trên máy này thì không hiện.
 */
export function ResumeCard() {
  const my = useMyCourses();
  const mounted = useMounted(); // bài gần nhất nằm trong localStorage, chỉ đọc được trên trình duyệt
  if (!mounted || !my.data) return null;
  const course = my.data.items.find((c) => !c.completed_at && lastLesson.get(c.course_id));
  if (!course) return null;
  return (
    <section
      aria-labelledby="resume-title"
      className="mb-8 flex flex-col gap-4 rounded-lg border bg-surface p-5 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm text-muted-foreground">Khóa bạn đang học</p>
        <h2 id="resume-title" className="mt-0.5 truncate text-lg font-semibold">
          {course.title}
        </h2>
        <div className="mt-3 max-w-sm">
          <Progress value={course.progress_pct} label={`Tiến độ ${course.title}`} />
          <p className="mt-1.5 text-xs text-muted-foreground">
            {course.done_lessons}/{course.total_lessons} bài · {course.progress_pct}%
          </p>
        </div>
      </div>
      <Button asChild size="lg" className="shrink-0">
        <Link href={resumeHref(course.course_id, course.slug)}>
          <PlayCircle /> Học tiếp
        </Link>
      </Button>
    </section>
  );
}

/** `moreHref`: hiện liên kết xem tất cả, chỉ khi còn khóa chưa hiện (tổng nhiều hơn `limit`). */
export function MyCourseList({ limit, moreHref }: { limit?: number; moreHref?: string }) {
  const my = useMyCourses();
  if (my.isPending) return <CardListSkeleton count={limit ?? 3} />;
  if (my.isError) return <ErrorState error={my.error} onRetry={() => my.refetch()} />;
  if (my.data.items.length === 0)
    return (
      <EmptyState
        icon={BookMarked}
        title="Bạn chưa đăng ký khóa học nào."
        action={
          <Button asChild>
            <Link href="/explore">Khám phá khóa học</Link>
          </Button>
        }
      />
    );
  const items = limit ? my.data.items.slice(0, limit) : my.data.items;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => (
          <CourseCard
            key={c.course_id}
            href={resumeHref(c.course_id, c.slug)}
            title={c.title}
            subtitle={c.completed_at ? "Đã hoàn thành" : undefined}
            progress={{ pct: c.progress_pct, done: c.done_lessons, total: c.total_lessons }}
          />
        ))}
      </div>
      {moreHref && my.data.total > items.length ? (
        <Button asChild variant="link" className="mt-4">
          <Link href={moreHref}>
            Xem tất cả {my.data.total} khóa của tôi <ArrowRight />
          </Link>
        </Button>
      ) : null}
    </>
  );
}
