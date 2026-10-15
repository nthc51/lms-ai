"use client";

import { ArrowRight, CirclePlay, Timer } from "lucide-react";
import Link from "next/link";
import { ErrorState } from "@/components/app/states";
import { CourseRows, pickResume } from "@/components/course/my-course-list";
import { Button } from "@/components/ui/button";
import { Progress, Skeleton } from "@/components/ui/misc";
import { useLesson, useMyCourses, usePendingQuizzes } from "@/lib/queries";
import { scrollPosition } from "@/lib/study/storage";
import { useMounted } from "@/lib/use-mounted";
import { cn } from "@/lib/utils";

const DAYS = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];

/** Trang tài liệu có một dòng được tô: cùng hình với trang chủ cho khách. */
function PageMotif() {
  return (
    <svg viewBox="0 0 120 160" className="h-auto w-[min(62%,220px)] transition-transform duration-500 group-hover:-translate-y-1.5 group-hover:-rotate-1" aria-hidden>
      <path d="M0 0h86l34 34v126H0z" className="fill-surface" />
      <path d="M86 0v34h34z" className="fill-foreground" />
      <g className="fill-foreground" opacity=".16">
        <rect x="14" y="22" width="56" height="7" />
        <rect x="14" y="44" width="90" height="5" />
        <rect x="14" y="56" width="84" height="5" />
        <rect x="14" y="68" width="90" height="5" />
        <rect x="14" y="104" width="78" height="5" />
        <rect x="14" y="116" width="90" height="5" />
        <rect x="14" y="128" width="60" height="5" />
      </g>
      <rect x="12" y="84" width="92" height="9" className="fill-mark" />
      <circle cx="106" cy="88.5" r="6" className="fill-foreground" />
    </svg>
  );
}

/** Tên bài đang học (tải bài từ API) và phần đã đọc (lưu trên máy). */
function LessonLine({ lessonId }: { lessonId: string }) {
  const lesson = useLesson(lessonId);
  const read = Math.round(scrollPosition.get(lessonId) * 100);
  if (lesson.isPending) return <Skeleton className="h-7 w-2/3 bg-foreground/10" />;
  if (lesson.isError) return null;
  return (
    <p className="max-w-[34ch] text-xl leading-snug md:text-2xl">
      <span className="bg-mark px-1 text-mark-foreground [box-decoration-break:clone]">{lesson.data.title}</span>
      {read >= 5 && read < 98 ? `, đã đọc khoảng ${read}%` : null}
    </p>
  );
}

/**
 * Trang chủ học viên: lời chào lớn, khối "đang học" (vào thẳng bài đang dở), ba con số, quiz chưa làm, khóa của tôi.
 * Nội dung trên khối màu luôn dùng màu chữ chính (màu phụ không đủ tương phản trên khối xanh đậm nhất).
 */
export function StudentHome({ givenName }: { givenName: string }) {
  const my = useMyCourses();
  const pending = usePendingQuizzes();
  const mounted = useMounted(); // ngày hôm nay và bài đang học (localStorage) chỉ có trên trình duyệt
  const items = my.data?.items ?? [];
  const resume = mounted ? pickResume(items) : null;
  const doing = items.filter((c) => !c.completed_at).length;
  const doneLessons = items.reduce((n, c) => n + c.done_lessons, 0);
  const finished = items.length - doing;
  const now = new Date();

  return (
    <div className="flex flex-col">
      <section aria-labelledby="h-hello" className="flex flex-wrap items-end justify-between gap-x-10 gap-y-4 pb-8 pt-4 md:pb-10 md:pt-8">
        <div className="min-w-0">
          <h1 id="h-hello" className="text-[clamp(2.75rem,1.6rem+4.6vw,5.5rem)] font-extrabold leading-[0.98] tracking-[-0.045em]">
            Chào {givenName}.
          </h1>
          <p className="mt-4 max-w-[46ch] text-lg leading-snug text-muted-foreground md:text-2xl">
            {resume
              ? `Còn ${resume.course.total_lessons - resume.course.done_lessons} bài trong khóa ${resume.course.title}. Học tiếp từ chỗ bạn đã dừng nhé.`
              : items.length
                ? "Bạn đã học xong mọi khóa đã đăng ký. Tìm khóa mới ở trang Khám phá."
                : "Bạn chưa đăng ký khóa nào. Bắt đầu từ trang Khám phá nhé."}
          </p>
        </div>
        {mounted ? (
          <p className="text-sm font-semibold text-muted-foreground md:text-right">
            <span className="block text-xl font-extrabold tracking-[-0.02em] text-foreground">
              {DAYS[now.getDay()]}, {now.getDate()}/{now.getMonth() + 1}
            </span>
            {doneLessons > 0 ? `Bạn đã học xong ${doneLessons} bài` : "Chúc bạn một buổi học tốt"}
          </p>
        ) : null}
      </section>

      {my.isPending ? (
        <Skeleton className="h-72 w-full" />
      ) : my.isError ? (
        <ErrorState error={my.error} onRetry={() => my.refetch()} />
      ) : resume ? (
        <>
          <section aria-labelledby="h-resume" className="group grid bg-field-1 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div className="flex flex-col gap-5 p-6 md:p-10">
              <h2 id="h-resume" className="text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.02] tracking-[-0.04em]">
                {resume.course.title}
              </h2>
              {resume.lessonId ? <LessonLine lessonId={resume.lessonId} /> : <p className="text-xl">Bạn chưa mở bài nào của khóa này trên máy này.</p>}
              <div className="flex max-w-md items-center gap-4 text-[15px] font-semibold">
                <Progress value={resume.course.progress_pct} label={`Tiến độ ${resume.course.title}`} className="flex-1 bg-foreground/15" />
                <span className="tabular-nums">
                  {resume.course.done_lessons}/{resume.course.total_lessons} bài · {resume.course.progress_pct}%
                </span>
              </div>
              <Button asChild size="lg" className="mt-auto h-14 text-base">
                <Link href={resume.lessonId ? `/learn/${resume.course.slug}/${resume.lessonId}` : `/courses/${resume.course.slug}`}>
                  <CirclePlay className="size-5" /> {resume.lessonId ? "Học tiếp" : "Vào khóa học"}
                </Link>
              </Button>
            </div>
            <div className="relative hidden place-items-center bg-field-3 px-8 pb-16 pt-8 md:grid">
              <PageMotif />
              <span className="absolute bottom-5 left-6 text-sm font-semibold">Mở lại đúng đoạn bạn đang đọc</span>
            </div>
          </section>
          <dl className="grid grid-cols-3 bg-surface">
            {(
              [
                [doing, "khóa đang học"],
                [doneLessons, "bài đã học xong"],
                [finished, "khóa đã hoàn thành"],
              ] as const
            ).map(([n, label], i) => (
              <div key={label} className={cn("flex flex-col-reverse px-4 py-5 md:px-8 md:py-7", i === 1 && "bg-background/60")}>
                <dt className="mt-2 text-[13px] font-semibold text-muted-foreground md:text-[15px]">{label}</dt>
                <dd className="text-[clamp(2.25rem,1.6rem+2vw,3.5rem)] font-extrabold leading-none tracking-[-0.05em] tabular-nums">{n}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}

      {pending.data && pending.data.length > 0 ? (
        <section aria-labelledby="h-next" className="mt-16 md:mt-24">
          <h2 id="h-next" className="mb-6 text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.05] tracking-[-0.04em]">
            Việc nên làm tiếp
          </h2>
          <ul className="grid gap-1.5 md:grid-cols-2">
            {pending.data.slice(0, 4).map((q, i) => (
              <li key={q.quiz_id}>
                <Link
                  href={`/learn/${q.course_slug}/${q.lesson_id}/quiz/${q.quiz_id}`}
                  className={cn("flex h-full items-start gap-4 p-5 transition-colors duration-150 md:p-6", i % 2 ? "bg-field-3 hover:bg-field-1" : "bg-field-2 hover:bg-field-1")}
                >
                  <span className="grid size-11 shrink-0 place-items-center bg-surface" aria-hidden>
                    <Timer className="size-5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[17px] font-semibold leading-snug">
                      {q.title} · {q.course_title}
                    </span>
                    <span className="mt-1 block text-[15px]">
                      {q.question_count} câu · {q.time_limit_sec ? `${Math.round(q.time_limit_sec / 60)} phút` : "không giới hạn giờ"} ·{" "}
                      {q.in_progress ? "đang làm dở" : "chưa làm"}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="h-mine" className="mt-16 md:mt-24">
        <div className="mb-6 flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="h-mine" className="text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.05] tracking-[-0.04em]">
            Khóa của tôi
          </h2>
          <Link href="/explore" className="inline-flex items-center gap-2 text-[15px] font-semibold text-primary underline-offset-4 hover:underline">
            Tìm thêm khóa học <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
        <CourseRows limit={3} moreHref="/my" />
      </section>
    </div>
  );
}
