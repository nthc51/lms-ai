"use client";

import { BookOpenCheck, Clock, Pencil, PlayCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { Markdown } from "@/components/content/markdown";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { flattenLessons, useCourse, useEnroll } from "@/lib/queries";
import { resumeLessonId } from "@/lib/study/resume";

export default function CourseDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const course = useCourse(slug);
  const enroll = useEnroll(slug);

  if (course.isPending)
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Đang tải">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (course.isError) return <ErrorState error={course.error} onRetry={() => course.refetch()} />;

  const c = course.data;
  const lessons = flattenLessons(c);
  const totalMin = Math.round(lessons.reduce((s, l) => s + (l.duration_sec ?? 0), 0) / 60);
  const resumeId = resumeLessonId(c);
  const learnHref = resumeId ? `/learn/${c.slug}/${resumeId}` : null;

  async function onEnroll() {
    if (!user) return router.push(`/login?next=${encodeURIComponent(`/courses/${slug}`)}`);
    try {
      await enroll.mutateAsync(c.id);
      toast.success("Đã đăng ký khóa học");
      if (lessons[0]) router.push(`/learn/${c.slug}/${lessons[0].id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <div>
        {c.status !== "published" ? <Badge tone="accent" className="mb-3">Bản nháp — học viên chưa thấy</Badge> : null}
        <h1 className="text-2xl font-semibold md:text-3xl">{c.title}</h1>
        <p className="mt-2 text-muted-foreground">
          Giảng viên {c.teacher_name} · {lessons.length} bài{totalMin ? ` · khoảng ${totalMin} phút video` : ""}
        </p>
        {c.description ? <Markdown className="mt-6">{c.description}</Markdown> : null}

        <h2 className="mt-10 text-xl font-semibold">Nội dung khóa học</h2>
        <ol className="mt-4 space-y-4">
          {[...c.sections]
            .sort((a, b) => a.position - b.position)
            .map((s, i) => (
              <li key={s.id} className="rounded-lg border bg-surface">
                <h3 className="border-b px-4 py-3 font-medium">
                  Chương {i + 1}. {s.title}
                </h3>
                <ul>
                  {[...s.lessons]
                    .sort((a, b) => a.position - b.position)
                    .map((l) => (
                      <li key={l.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                        {c.is_enrolled || c.is_owner ? (
                          <Link href={`/learn/${c.slug}/${l.id}`} className="hover:text-primary hover:underline">
                            {l.title}
                          </Link>
                        ) : (
                          <span>{l.title}</span>
                        )}
                        {l.duration_sec ? (
                          <span className="flex shrink-0 items-center gap-1 text-muted-foreground">
                            <Clock className="size-3.5" aria-hidden />
                            {Math.ceil(l.duration_sec / 60)} phút
                          </span>
                        ) : null}
                      </li>
                    ))}
                </ul>
              </li>
            ))}
        </ol>
      </div>

      {/* Hộp hành động: dính bên phải trên desktop, dính đáy trên điện thoại */}
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className="fixed inset-x-0 bottom-16 z-20 border-t bg-surface p-3 md:static md:rounded-lg md:border md:p-5">
          {c.is_owner ? (
            <Button asChild size="lg" className="w-full">
              <Link href={`/teach/${c.slug}`}>
                <Pencil /> Chỉnh sửa khóa học
              </Link>
            </Button>
          ) : c.is_enrolled ? (
            learnHref ? (
              <Button asChild size="lg" className="w-full">
                <Link href={learnHref}>
                  <PlayCircle /> Học tiếp
                </Link>
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">Khóa học chưa có bài nào.</p>
            )
          ) : user && user.role !== "student" ? (
            <p className="text-sm text-muted-foreground">Chỉ tài khoản học viên mới đăng ký được khóa học.</p>
          ) : (
            <Button size="lg" className="w-full" onClick={onEnroll} loading={enroll.isPending} loadingText="Đang đăng ký…">
              <BookOpenCheck /> Đăng ký khóa học
            </Button>
          )}
        </div>
      </aside>
    </div>
  );
}
