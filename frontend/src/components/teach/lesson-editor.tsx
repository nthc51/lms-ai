"use client";

import { ArrowLeft, Eye, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Tabs } from "radix-ui";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { Markdown } from "@/components/content/markdown";
import { CourseOutline } from "@/components/lesson/course-outline";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { api, unwrap } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { type LessonDetail, qk, useCourse, useLesson, useLessonVideo } from "@/lib/queries";
import { autosaveLabel, useAutosave } from "@/lib/use-autosave";
import { useQueryClient } from "@tanstack/react-query";
import { FileDrop, readVideoDuration } from "./file-drop";
import { SourceList } from "./source-list";

export function LessonEditor({ slug, lessonId }: { slug: string; lessonId: string }) {
  const course = useCourse(slug);
  const lesson = useLesson(lessonId);

  if (course.isError || lesson.isError)
    return <ErrorState error={course.error ?? lesson.error} onRetry={() => (course.refetch(), lesson.refetch())} />;

  return (
    <div className="grid gap-6 lg:grid-cols-[240px_1fr_320px]">
      <aside className="hidden lg:block">
        <Link href={`/teach/${slug}`} className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:underline">
          <ArrowLeft className="size-4" aria-hidden /> {course.data?.title ?? "Khóa học"}
        </Link>
        {course.data ? <EditorOutline course={course.data} slug={slug} lessonId={lessonId} /> : <Skeleton className="h-60" />}
      </aside>
      {lesson.isPending ? (
        <div className="space-y-4" aria-busy="true" aria-label="Đang tải">
          <Skeleton className="h-10 w-2/3" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : (
        <>
          <Content key={lesson.data.id} lesson={lesson.data} slug={slug} />
          <div className="space-y-8">
            <VideoBox lessonId={lessonId} />
            <SourceList lessonId={lessonId} />
          </div>
        </>
      )}
    </div>
  );
}

/** Mục lục trong trình soạn: các link trỏ về trình soạn bài, không phải trang học. */
function EditorOutline({ course, slug, lessonId }: { course: Parameters<typeof CourseOutline>[0]["course"]; slug: string; lessonId: string }) {
  return (
    <CourseOutline course={course} currentLessonId={lessonId} hrefFor={(id) => `/teach/${slug}/lessons/${id}`} />
  );
}

function Content({ lesson, slug }: { lesson: LessonDetail; slug: string }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [value, setValue] = React.useState({ title: lesson.title, content_md: lesson.content_md });
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const titleEmpty = !value.title.trim();
  const deleted = React.useRef(false); // bài đã xóa thì không lưu nốt khi rời trang
  const autosave = useAutosave(
    value,
    async (v) => {
      await unwrap(
        api.PATCH("/api/v1/lessons/{lesson_id}", {
          params: { path: { lesson_id: lesson.id } },
          body: { title: v.title.trim(), content_md: v.content_md },
        }),
      );
      qc.setQueryData<LessonDetail>(qk.lesson(lesson.id), (old) => (old ? { ...old, ...v } : old));
      if (v.title !== lesson.title) qc.invalidateQueries({ queryKey: qk.course(slug) });
    },
    { enabled: !titleEmpty },
  );

  // Rời trang/đổi bài: lưu ngay phần đang chờ (hook chỉ dọn timer). Tên trống hoặc bài đã xóa thì không lưu.
  const flushRef = React.useRef(autosave.flush);
  const titleEmptyRef = React.useRef(titleEmpty);
  React.useEffect(() => {
    flushRef.current = autosave.flush;
    titleEmptyRef.current = titleEmpty;
  });
  React.useEffect(
    () => () => {
      if (!titleEmptyRef.current && !deleted.current) void flushRef.current();
    },
    [],
  );

  // rời trang khi còn thay đổi chưa lưu → trình duyệt hỏi lại
  React.useEffect(() => {
    const dirty = autosave.state.status === "dirty" || autosave.state.status === "saving";
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [autosave.state.status]);

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/teach/${slug}`} className="flex items-center gap-1 text-sm text-muted-foreground hover:underline lg:hidden">
          <ArrowLeft className="size-4" aria-hidden /> Về khóa học
        </Link>
        <span aria-live="polite" className="ml-auto text-sm text-muted-foreground">
          {autosaveLabel(autosave.state)}
        </span>
        <Button variant="outline" size="sm" className="h-10 md:h-8" onClick={() => void autosave.flush()} disabled={titleEmpty}>
          <Save /> Lưu
        </Button>
        <Button asChild variant="outline" size="sm" className="h-10 md:h-8">
          <Link href={`/learn/${slug}/${lesson.id}`}>
            <Eye /> Xem như học viên
          </Link>
        </Button>
      </div>

      <Field id="l-title" label="Tên bài" error={titleEmpty ? "Tên bài không được trống" : undefined}>
        <Input value={value.title} maxLength={200} onChange={(e) => setValue((v) => ({ ...v, title: e.target.value }))} />
      </Field>

      <Tabs.Root defaultValue="write">
        <Tabs.List aria-label="Nội dung bài" className="inline-flex rounded-md border p-0.5">
          {[
            ["write", "Soạn"],
            ["preview", "Xem trước"],
          ].map(([v, l]) => (
            <Tabs.Trigger
              key={v}
              value={v}
              className="h-9 rounded px-3 text-sm data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
            >
              {l}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="write" className="mt-3">
          <label htmlFor="l-content" className="sr-only">
            Nội dung bài (markdown)
          </label>
          <textarea
            id="l-content"
            value={value.content_md}
            maxLength={100_000}
            onChange={(e) => setValue((v) => ({ ...v, content_md: e.target.value }))}
            placeholder={"# Tiêu đề\n\nNội dung markdown. Công thức: $E = mc^2$"}
            className="min-h-[60dvh] w-full rounded-md border bg-surface p-4 font-mono text-sm leading-relaxed"
          />
          <p className="mt-1 text-xs text-muted-foreground">Hỗ trợ Markdown, bảng, công thức LaTeX ($…$ và $$…$$). Tự lưu sau 1 giây ngừng gõ.</p>
        </Tabs.Content>
        <Tabs.Content value="preview" className="mt-3 rounded-md border bg-surface p-4 md:p-6">
          {value.content_md ? <Markdown>{value.content_md}</Markdown> : <p className="text-muted-foreground">Chưa có nội dung.</p>}
        </Tabs.Content>
      </Tabs.Root>

      <div className="border-t pt-4">
        <Button variant="destructive-outline" onClick={() => setDeleteOpen(true)}>
          <Trash2 /> Xóa bài này
        </Button>
      </div>
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        destructive
        title={`Xóa bài “${lesson.title}”?`}
        description="Nội dung, video, tài liệu PDF và tiến độ học của bài sẽ bị xóa và không khôi phục được."
        confirmLabel="Xóa bài"
        pendingLabel="Đang xóa…"
        onConfirm={async () => {
          try {
            await unwrap(api.DELETE("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: lesson.id } } }));
            deleted.current = true;
            qc.invalidateQueries({ queryKey: qk.course(slug) });
            toast.success("Đã xóa bài");
            router.replace(`/teach/${slug}`);
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </div>
  );
}

function VideoBox({ lessonId }: { lessonId: string }) {
  const qc = useQueryClient();
  const video = useLessonVideo(lessonId);
  const [removeOpen, setRemoveOpen] = React.useState(false);

  const patch = (body: { video_asset_id: string | null; duration_sec: number | null }) =>
    unwrap(api.PATCH("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: lessonId } }, body }));
  const refresh = () => {
    qc.invalidateQueries({ queryKey: qk.lessonVideo(lessonId) });
    qc.invalidateQueries({ queryKey: ["course"] });
  };

  return (
    <section aria-labelledby="video-title" className="space-y-3">
      <h2 id="video-title" className="font-semibold">
        Video bài giảng
      </h2>
      {video.isPending ? (
        <Skeleton className="aspect-video w-full" />
      ) : video.data ? (
        <>
          <video src={video.data} controls preload="metadata" className="aspect-video w-full rounded-md bg-black" />
          <Button variant="destructive-outline" size="sm" className="h-10 md:h-8" onClick={() => setRemoveOpen(true)}>
            <Trash2 /> Gỡ video
          </Button>
        </>
      ) : null}
      <FileDrop
        kind="video"
        label={video.data ? "Thay video khác" : "Chọn file MP4"}
        onUploaded={async (assetId, file) => {
          const duration = await readVideoDuration(file);
          await patch({ video_asset_id: assetId, duration_sec: duration });
          refresh();
          toast.success("Đã gắn video vào bài");
        }}
      />
      <ConfirmDialog
        open={removeOpen}
        onOpenChange={setRemoveOpen}
        destructive
        title="Gỡ video khỏi bài?"
        description="Học viên sẽ không xem được video này nữa."
        confirmLabel="Gỡ video"
        pendingLabel="Đang gỡ…"
        onConfirm={async () => {
          try {
            await patch({ video_asset_id: null, duration_sec: null });
            refresh();
            toast.success("Đã gỡ video");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </section>
  );
}
