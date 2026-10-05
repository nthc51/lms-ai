"use client";

import { BookMarked } from "lucide-react";
import Link from "next/link";
import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
import { CourseCard } from "@/components/course/course-card";
import { Button } from "@/components/ui/button";
import { useMyCourses } from "@/lib/queries";
import { lastLesson } from "@/lib/study/storage";

/** Có bài mở gần nhất trên máy này → vào thẳng bài đó; không thì mở trang khóa. */
function resumeHref(courseId: string, slug: string) {
  const last = lastLesson.get(courseId);
  return last ? `/learn/${slug}/${last}` : `/courses/${slug}`;
}

export function MyCourseList({ limit }: { limit?: number }) {
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
  );
}
