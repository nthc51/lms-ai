"use client";

import {
  AArrowDown,
  AArrowUp,
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Keyboard,
  ListTree,
  Maximize2,
  MessageCircleQuestion,
  Minimize2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ThemeSwitcher } from "@/components/app/theme-switcher";
import { ErrorState } from "@/components/app/states";
import { Markdown } from "@/components/content/markdown";
import { TutorPanel } from "@/components/tutor/tutor-panel";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Badge, Skeleton, Tip } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { attachVideoRef } from "@/lib/study/video-ref";
import { flattenLessons, useCourse, useLesson, useLessonVideo, useSaveProgress } from "@/lib/queries";
import { lastLesson, READER_MAX, READER_MIN, readerSize } from "@/lib/study/storage";
import { useShortcuts } from "@/lib/study/use-shortcuts";
import { useVideoProgress } from "@/lib/study/use-video-progress";
import { useTutorChat } from "@/lib/tutor/use-tutor-chat";
import { cn } from "@/lib/utils";
import { BreakReminder } from "./break-reminder";
import { CourseOutline } from "./course-outline";
import { ReadingProgress } from "./reading-progress";
import { ShortcutHelp } from "./shortcut-help";

function useIsDesktop() {
  const [desktop, setDesktop] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return desktop;
}

export function LessonView({ slug, lessonId }: { slug: string; lessonId: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const course = useCourse(slug);
  const lesson = useLesson(lessonId);
  const video = useLessonVideo(lessonId);
  const desktop = useIsDesktop();

  // LessonView chỉ render trên trình duyệt (sau RequireAuth) nên đọc localStorage lúc khởi tạo được
  const [fontPx, setFontPx] = React.useState(() => readerSize.get());
  const [focus, setFocus] = React.useState(false);
  const [outlineOpen, setOutlineOpen] = React.useState(true); // desktop
  const [outlineSheet, setOutlineSheet] = React.useState(false); // điện thoại
  const [tutorOpen, setTutorOpen] = React.useState(false);
  const [helpOpen, setHelpOpen] = React.useState(false);
  const videoRef = React.useRef<HTMLVideoElement | null>(null);

  const changeFont = (d: number) => {
    const next = Math.min(READER_MAX, Math.max(READER_MIN, fontPx + d));
    setFontPx(next);
    readerSize.set(next);
  };

  const lessons = course.data ? flattenLessons(course.data) : [];
  const index = lessons.findIndex((l) => l.id === lessonId);
  const prev = index > 0 ? lessons[index - 1] : null;
  const next = index >= 0 && index < lessons.length - 1 ? lessons[index + 1] : null;
  const go = (id: string) => router.push(`/learn/${slug}/${id}`);

  React.useEffect(() => {
    if (course.data) lastLesson.set(course.data.id, lessonId);
  }, [course.data, lessonId]);

  const chat = useTutorChat({ courseId: course.data?.id ?? "", lessonId }, !!course.data && tutorOpen);

  useShortcuts({
    "/": () => setTutorOpen(true),
    f: () => setFocus((v) => !v),
    ArrowLeft: () => prev && go(prev.id),
    ArrowRight: () => next && go(next.id),
    Escape: () => (tutorOpen ? setTutorOpen(false) : setFocus(false)),
    "?": () => setHelpOpen(true),
  });

  if (course.isError || lesson.isError)
    return (
      <div className="p-6">
        <ErrorState
          error={course.error ?? lesson.error}
          onRetry={() => {
            course.refetch();
            lesson.refetch();
          }}
        />
      </div>
    );

  const isStudent = user?.role === "student";
  const seek = (sec: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = sec;
    v.scrollIntoView({ behavior: "smooth", block: "center" });
    void v.play().catch(() => undefined);
  };
  const openLesson = (id: string) => {
    setTutorOpen(false);
    go(id);
  };
  const tutor = course.data ? (
    <TutorPanel chat={chat} lessonId={lessonId} onSeek={seek} onOpenLesson={openLesson} />
  ) : null;

  return (
    <div className="min-h-dvh" style={{ ["--reader-size" as string]: `${fontPx}px` }}>
      <ReadingProgress lessonId={lessonId} ready={!!lesson.data} />

      {/* Thanh trên cùng */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-1 border-b bg-background/95 px-2 backdrop-blur md:px-4">
        <Button asChild variant="ghost" size="icon" aria-label="Về trang khóa học">
          <Link href={`/courses/${slug}`}>
            <ArrowLeft />
          </Link>
        </Button>
        <Tip label="Mục lục">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Mục lục"
            aria-expanded={desktop ? outlineOpen && !focus : outlineSheet}
            onClick={() => (desktop ? setOutlineOpen((v) => !v) : setOutlineSheet(true))}
          >
            <ListTree />
          </Button>
        </Tip>
        <p className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{course.data?.title}</p>
        <div className="hidden items-center gap-1 md:flex">
          <Tip label="Chữ nhỏ hơn">
            <Button variant="ghost" size="icon" aria-label="Chữ nhỏ hơn" disabled={fontPx <= READER_MIN} onClick={() => changeFont(-1)}>
              <AArrowDown />
            </Button>
          </Tip>
          <Tip label="Chữ lớn hơn">
            <Button variant="ghost" size="icon" aria-label="Chữ lớn hơn" disabled={fontPx >= READER_MAX} onClick={() => changeFont(1)}>
              <AArrowUp />
            </Button>
          </Tip>
          <ThemeSwitcher compact />
          <Tip label={focus ? "Thoát chế độ tập trung (F)" : "Chế độ tập trung (F)"}>
            <Button variant="ghost" size="icon" aria-label="Chế độ tập trung" aria-pressed={focus} onClick={() => setFocus((v) => !v)}>
              {focus ? <Minimize2 /> : <Maximize2 />}
            </Button>
          </Tip>
          <Tip label="Phím tắt (?)">
            <Button variant="ghost" size="icon" aria-label="Phím tắt" onClick={() => setHelpOpen(true)}>
              <Keyboard />
            </Button>
          </Tip>
        </div>
        <Button variant="ghost" className="hidden lg:inline-flex" aria-pressed={tutorOpen} onClick={() => setTutorOpen((v) => !v)}>
          <MessageCircleQuestion /> Hỏi AI
        </Button>
      </header>

      <div className="flex">
        {/* Mục lục bên trái (desktop) */}
        {desktop && outlineOpen && !focus && course.data ? (
          <aside className="sticky top-14 h-[calc(100dvh-3.5rem)] w-72 shrink-0 overflow-y-auto border-r">
            <CourseOutline course={course.data} currentLessonId={lessonId} />
          </aside>
        ) : null}

        {/* Nội dung bài */}
        <main id="main" className="min-w-0 flex-1 px-4 pb-28 pt-6 md:px-8 lg:pb-12">
          <article className="mx-auto max-w-[68ch]" style={{ maxWidth: `calc(68ch * ${fontPx} / 16)` }}>
            {lesson.isPending ? (
              <div className="space-y-4" aria-busy="true" aria-label="Đang tải bài học">
                <Skeleton className="h-8 w-2/3" />
                <Skeleton className="aspect-video w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
              </div>
            ) : (
              <>
                {!isStudent ? <Badge tone="accent" className="mb-3">Chế độ xem trước — tiến độ không được lưu</Badge> : null}
                <p className="text-sm text-muted-foreground">
                  Bài {index + 1}/{lessons.length}
                  {lessons[index]?.sectionTitle ? ` · ${lessons[index].sectionTitle}` : ""}
                </p>
                <h1 className="mt-1 text-2xl font-semibold md:text-3xl">{lesson.data.title}</h1>

                {video.data ? (
                  <LessonVideo
                    key={lessonId}
                    src={video.data}
                    lesson={lesson.data}
                    track={isStudent}
                    videoRef={videoRef}
                  />
                ) : null}

                {lesson.data.content_md ? (
                  <Markdown className="mt-6">{lesson.data.content_md}</Markdown>
                ) : (
                  <p className="mt-6 text-muted-foreground">Bài này chưa có nội dung đọc.</p>
                )}

                <LessonFooter
                  lesson={lesson.data}
                  isStudent={isStudent}
                  prev={prev}
                  next={next}
                  onGo={go}
                  videoRef={videoRef}
                />
              </>
            )}
          </article>
        </main>

        {/* Tutor bên phải (desktop) */}
        {desktop && tutorOpen ? (
          <aside aria-label="AI Tutor" className="sticky top-14 flex h-[calc(100dvh-3.5rem)] w-[400px] shrink-0 flex-col border-l bg-surface">
            <div className="flex h-12 items-center justify-between border-b px-4">
              <h2 className="font-semibold">AI Tutor</h2>
              <Button variant="ghost" size="icon" aria-label="Đóng AI Tutor" onClick={() => setTutorOpen(false)}>
                <X />
              </Button>
            </div>
            <div className="min-h-0 flex-1">{tutor}</div>
          </aside>
        ) : null}
      </div>

      {/* Điện thoại: nút nổi + khung trượt */}
      {!desktop ? (
        <>
          <Button size="lg" className="fixed bottom-4 right-4 z-30 rounded-full shadow-lg" onClick={() => setTutorOpen(true)}>
            <MessageCircleQuestion /> Hỏi AI
          </Button>
          <Sheet open={tutorOpen} onOpenChange={setTutorOpen} title="AI Tutor">
            {tutor}
          </Sheet>
          <Sheet open={outlineSheet} onOpenChange={setOutlineSheet} title="Mục lục" side="left">
            <div className="h-full overflow-y-auto">
              {course.data ? (
                <CourseOutline course={course.data} currentLessonId={lessonId} onNavigate={() => setOutlineSheet(false)} />
              ) : null}
            </div>
          </Sheet>
        </>
      ) : null}

      <ShortcutHelp open={helpOpen} onOpenChange={setHelpOpen} />
      <BreakReminder />
    </div>
  );
}

function LessonVideo({
  src,
  lesson,
  track,
  videoRef,
}: {
  src: string;
  lesson: NonNullable<ReturnType<typeof useLesson>["data"]>;
  track: boolean;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const { bind } = useVideoProgress(lesson, track);
  const setRef = React.useCallback(
    (el: HTMLVideoElement | null) => attachVideoRef(videoRef, bind, el),
    [bind, videoRef],
  );
  return (
    // Điện thoại: video dính trên cùng khi cuộn (design-system §7.2)
    <div className="sticky top-14 z-20 -mx-4 mt-4 bg-background md:static md:mx-0">
      <video ref={setRef} src={src} controls playsInline preload="metadata" className="aspect-video w-full bg-black md:rounded-lg">
        Trình duyệt không phát được video này.
      </video>
    </div>
  );
}

function LessonFooter({
  lesson,
  isStudent,
  prev,
  next,
  onGo,
  videoRef,
}: {
  lesson: NonNullable<ReturnType<typeof useLesson>["data"]>;
  isStudent: boolean;
  prev: { id: string; title: string } | null;
  next: { id: string; title: string } | null;
  onGo: (id: string) => void;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const save = useSaveProgress(lesson.id);
  const done = lesson.progress?.status === "done";

  async function markDone() {
    try {
      await save.mutateAsync({ status: "done", video_position_sec: Math.floor(videoRef.current?.currentTime ?? lesson.progress?.video_position_sec ?? 0) });
      toast.success("Đã đánh dấu học xong");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="mt-10 border-t pt-6">
      {isStudent ? (
        done ? (
          <p className="flex items-center gap-2 font-medium text-success">
            <CheckCircle2 className="size-5" aria-hidden /> Đã học xong bài này
          </p>
        ) : (
          <Button variant="outline" onClick={markDone} loading={save.isPending} loadingText="Đang lưu…">
            <CheckCircle2 /> Đánh dấu đã học xong
          </Button>
        )
      ) : null}
      <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        {prev ? (
          <Button variant="outline" onClick={() => onGo(prev.id)} className="justify-start">
            <ChevronLeft /> <span className="truncate">Bài trước: {prev.title}</span>
          </Button>
        ) : (
          <span />
        )}
        {next ? (
          // Bài tiếp là nút chính khi đã học xong (gợi ý bước tiếp theo); trước đó là nút phụ
          <Button variant={done || !isStudent ? "default" : "outline"} onClick={() => onGo(next.id)} className={cn("justify-end")}>
            <span className="truncate">Bài tiếp: {next.title}</span> <ChevronRight />
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">Đây là bài cuối của khóa.</p>
        )}
      </div>
    </div>
  );
}
