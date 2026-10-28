import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import type { CourseDetail } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Mục lục khóa trong trang học bài; bài đang mở được đánh dấu aria-current, bài đã học xong có dấu tích
 * (mặc định lấy từ `course.done_lesson_ids`, chỉ có khi người xem đã đăng ký khóa). */
export function CourseOutline({
  course,
  currentLessonId,
  doneIds,
  onNavigate,
  hrefFor = (id) => `/learn/${course.slug}/${id}`,
}: {
  course: CourseDetail;
  currentLessonId: string;
  doneIds?: ReadonlySet<string>;
  onNavigate?: () => void;
  /** Link của mỗi bài; mặc định là trang học, trình soạn truyền link soạn bài. */
  hrefFor?: (lessonId: string) => string;
}) {
  const done = doneIds ?? new Set(course.done_lesson_ids ?? []);
  return (
    <nav aria-label="Mục lục khóa học" className="space-y-4 p-3">
      {[...course.sections]
        .sort((a, b) => a.position - b.position)
        .map((s, i) => (
          <div key={s.id}>
            <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Chương {i + 1}. {s.title}
            </p>
            <ul className="mt-1">
              {[...s.lessons]
                .sort((a, b) => a.position - b.position)
                .map((l) => {
                  const current = l.id === currentLessonId;
                  const isDone = done.has(l.id);
                  return (
                    <li key={l.id}>
                      <Link
                        href={hrefFor(l.id)}
                        onClick={onNavigate}
                        aria-current={current ? "page" : undefined}
                        className={cn(
                          "flex min-h-10 items-start gap-2 rounded-md px-2 py-2 text-sm hover:bg-muted",
                          current && "bg-muted font-medium text-primary",
                        )}
                      >
                        {isDone ? (
                          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="Đã học" />
                        ) : (
                          <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                        )}
                        {l.title}
                      </Link>
                    </li>
                  );
                })}
            </ul>
          </div>
        ))}
    </nav>
  );
}
