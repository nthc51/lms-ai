"use client";

import { ArrowRight, BookMarked } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/misc";
import type { components } from "@/lib/api/schema";
import { useMyCourses } from "@/lib/queries";
import { lastLesson } from "@/lib/study/storage";
import { cn } from "@/lib/utils";

export type MyCourse = components["schemas"]["MyCourseOut"];

/** Có bài mở gần nhất trên máy này → vào thẳng bài đó; không thì mở trang khóa. */
export function resumeHref(courseId: string, slug: string) {
  const last = lastLesson.get(courseId);
  return last ? `/learn/${slug}/${last}` : `/courses/${slug}`;
}

/** Khóa để "học tiếp": khóa chưa xong đầu tiên mà máy này còn nhớ bài đang học; không có thì khóa chưa xong đầu tiên. */
export function pickResume(items: MyCourse[]): { course: MyCourse; lessonId: string | null } | null {
  const open = items.filter((c) => !c.completed_at);
  for (const c of open) {
    const lessonId = lastLesson.get(c.course_id);
    if (lessonId) return { course: c, lessonId };
  }
  return open[0] ? { course: open[0], lessonId: null } : null;
}

/** "02/09": ngày/tháng theo giờ máy, không phụ thuộc cách trình duyệt định dạng locale. */
const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
};

function NoCourses() {
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
}

/**
 * Danh sách khóa dạng hàng (trang chủ): tên khóa, thanh tiến độ, số bài. `moreHref`: liên kết xem tất cả, chỉ hiện
 * khi còn khóa chưa hiện (tổng nhiều hơn `limit`).
 */
export function CourseRows({ limit, moreHref }: { limit?: number; moreHref?: string }) {
  const my = useMyCourses();
  if (my.isPending) return <CardListSkeleton count={limit ?? 3} />;
  if (my.isError) return <ErrorState error={my.error} onRetry={() => my.refetch()} />;
  if (my.data.items.length === 0) return <NoCourses />;
  const items = limit ? my.data.items.slice(0, limit) : my.data.items;
  return (
    <>
      <ul className="flex flex-col gap-1.5">
        {items.map((c) => (
          <li key={c.course_id}>
            <Link
              href={resumeHref(c.course_id, c.slug)}
              className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-3 bg-surface px-4 py-5 transition-colors duration-150 hover:bg-field-3 md:grid-cols-[minmax(0,1.4fr)_minmax(140px,1fr)_auto_auto] md:px-6"
            >
              <span className="min-w-0">
                <span className="block truncate text-lg font-semibold tracking-[-0.02em] md:text-xl">{c.title}</span>
                <span className="mt-0.5 block text-sm text-muted-foreground">
                  {c.completed_at ? `Đã hoàn thành ${fmtDate(c.completed_at)}` : `Đăng ký ${fmtDate(c.enrolled_at)}`}
                </span>
              </span>
              <Progress
                value={c.progress_pct}
                label={`Tiến độ ${c.title}`}
                className="col-span-2 row-start-2 md:col-span-1 md:row-start-auto"
              />
              <span className="text-right text-[15px] font-semibold tabular-nums">
                {c.done_lessons}/{c.total_lessons} bài
              </span>
              <ArrowRight
                className="hidden size-5 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-primary md:block"
                aria-hidden
              />
            </Link>
          </li>
        ))}
      </ul>
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

const TILE_COLORS = ["bg-field-1", "bg-field-2", "bg-surface", "bg-field-3"];

/** Lưới khối: khối đầu rộng 7/12, khối hai 5/12, các khối sau 6/12; khối lẻ cuối cùng trải hết hàng. */
function tileSpan(i: number, n: number) {
  if (i === 0) return n === 1 ? "md:col-span-12" : "md:col-span-7";
  if (i === 1) return "md:col-span-5";
  const lastAlone = i === n - 1 && (n - 2) % 2 === 1;
  return lastAlone ? "md:col-span-12" : "md:col-span-6";
}

/** Trang Khóa của tôi: hai nhóm Đang học / Đã xong, mỗi khóa là một khối màu có tiến độ và lối vào học tiếp. */
export function CourseBoard() {
  const my = useMyCourses();
  const [tab, setTab] = React.useState<"doing" | "done">("doing");
  if (my.isPending) return <CardListSkeleton />;
  if (my.isError) return <ErrorState error={my.error} onRetry={() => my.refetch()} />;
  if (my.data.items.length === 0) return <NoCourses />;
  const doing = my.data.items.filter((c) => !c.completed_at);
  const done = my.data.items.filter((c) => c.completed_at);
  const shown = tab === "doing" ? doing : done;
  return (
    <>
      <div role="group" aria-label="Lọc khóa học" className="mb-6 flex gap-1.5">
        {(
          [
            ["doing", `Đang học · ${doing.length}`],
            ["done", `Đã xong · ${done.length}`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "h-11 px-4 text-[15px] font-semibold transition-colors duration-150",
              tab === key ? "bg-brand text-white" : "bg-surface text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="bg-surface p-8 text-lg text-muted-foreground">
          {tab === "doing" ? "Bạn đã học xong mọi khóa đã đăng ký." : "Chưa có khóa nào học xong."}
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-1.5 md:grid-cols-12">
          {shown.map((c, i) => (
            <li key={c.course_id} className={tileSpan(i, shown.length)}>
              <Link
                href={resumeHref(c.course_id, c.slug)}
                className={cn(
                  "flex h-full min-h-52 flex-col gap-2 p-6 transition-transform duration-300 hover:-translate-y-1 md:p-8",
                  TILE_COLORS[i % TILE_COLORS.length],
                )}
              >
                <span className="text-[clamp(1.375rem,1.1rem+1vw,2.125rem)] font-extrabold leading-[1.08] tracking-[-0.035em]">
                  {c.title}
                </span>
                <span className="text-sm font-semibold">
                  {c.completed_at ? `Hoàn thành ${fmtDate(c.completed_at)}` : `Đăng ký ${fmtDate(c.enrolled_at)}`}
                </span>
                <span className="mt-auto flex flex-col gap-2.5 pt-6">
                  <Progress value={c.progress_pct} label={`Tiến độ ${c.title}`} className="bg-foreground/15" />
                  <span className="flex justify-between text-[15px] font-semibold tabular-nums">
                    <span>
                      {c.done_lessons}/{c.total_lessons} bài
                    </span>
                    <span>{c.progress_pct}%</span>
                  </span>
                  <span className="inline-flex items-center gap-2 text-[15px] font-semibold underline-offset-4 group-hover:underline">
                    {c.completed_at ? "Xem lại khóa" : c.done_lessons > 0 || lastLesson.get(c.course_id) ? "Học tiếp" : "Bắt đầu học"}
                    <ArrowRight className="size-4" aria-hidden />
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
