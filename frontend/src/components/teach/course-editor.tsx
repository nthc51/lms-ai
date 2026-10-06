"use client";

import { BarChart3, Eye, Globe, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type CourseDetail, flattenLessons, useCourse } from "@/lib/queries";
import { useCourseMutations } from "@/lib/teach-queries";
import { autosaveLabel, useAutosave } from "@/lib/use-autosave";
import { Curriculum } from "./curriculum";

export function CourseEditor({ slug }: { slug: string }) {
  const course = useCourse(slug);
  if (course.isPending)
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Đang tải">
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  if (course.isError) return <ErrorState error={course.error} onRetry={() => course.refetch()} />;
  return <Editor key={course.data.id} course={course.data} />;
}

function Editor({ course }: { course: CourseDetail }) {
  const router = useRouter();
  const mut = useCourseMutations(course);
  const [publishOpen, setPublishOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const deleted = React.useRef(false); // khóa đã xóa thì CourseInfo không lưu nốt khi đóng trình soạn
  const firstLesson = flattenLessons(course)[0];
  const empty = !firstLesson;

  return (
    <>
      {/* Thanh trên cùng: duy nhất 1 nút chính (Xuất bản) */}
      <div className="mb-6 flex flex-wrap items-center gap-3 md:mb-8">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted-foreground">
            <Link href="/teach" className="hover:underline">
              Khóa đang dạy
            </Link>{" "}
            ›
          </p>
          <h1 className="truncate text-2xl font-semibold md:text-3xl">{course.title}</h1>
        </div>
        {course.status === "published" ? <Badge tone="success">Đã xuất bản</Badge> : <Badge>Nháp</Badge>}
        <Button asChild variant="outline">
          <Link href={`/teach/${course.slug}/analytics`}>
            <BarChart3 /> Thống kê
          </Link>
        </Button>
        {firstLesson ? (
          <Button asChild variant="outline">
            <Link href={`/learn/${course.slug}/${firstLesson.id}`}>
              <Eye /> Xem như học viên
            </Link>
          </Button>
        ) : null}
        {course.status !== "published" ? (
          <div className="flex flex-col items-end gap-1">
            <Button onClick={() => setPublishOpen(true)} disabled={empty} aria-describedby={empty ? "publish-hint" : undefined}>
              <Globe /> Xuất bản
            </Button>
            {empty ? (
              <p id="publish-hint" className="text-xs text-muted-foreground">
                Thêm ít nhất 1 bài để xuất bản
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <p className="mb-6 rounded-md border border-dashed p-3 text-sm text-muted-foreground md:hidden">
        Soạn nội dung dài nên dùng máy tính. Trên điện thoại bạn vẫn sửa tên, nội dung ngắn và thứ tự được.
      </p>

      <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
        <Curriculum course={course} mut={mut} />
        <div className="space-y-8">
          <CourseInfo course={course} mut={mut} deleted={deleted} />
          <section className="rounded-lg border border-destructive/30 p-4">
            <h2 className="font-semibold">Vùng nguy hiểm</h2>
            <p className="mt-1 text-sm text-muted-foreground">Xóa khóa học cùng toàn bộ chương, bài và tài liệu.</p>
            <Button variant="destructive-outline" className="mt-3" onClick={() => setDeleteOpen(true)}>
              <Trash2 /> Xóa khóa học
            </Button>
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        title="Xuất bản khóa học?"
        description="Học viên sẽ tìm thấy và đăng ký được khóa học này. Bạn vẫn sửa nội dung được sau khi xuất bản."
        confirmLabel="Xuất bản"
        pendingLabel="Đang xuất bản…"
        onConfirm={async () => {
          try {
            await mut.publish.mutateAsync(undefined);
            toast.success("Khóa học đã được xuất bản");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        destructive
        title={`Xóa khóa học “${course.title}”?`}
        description={`Khóa có ${flattenLessons(course).length} bài. Mọi nội dung, video, tài liệu sẽ bị xóa vĩnh viễn.`}
        confirmText={course.title}
        confirmLabel="Xóa vĩnh viễn"
        pendingLabel="Đang xóa…"
        onConfirm={async () => {
          try {
            await mut.deleteCourse.mutateAsync();
            deleted.current = true;
            toast.success("Đã xóa khóa học");
            router.replace("/teach");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </>
  );
}

function CourseInfo({
  course,
  mut,
  deleted,
}: {
  course: CourseDetail;
  mut: ReturnType<typeof useCourseMutations>;
  deleted: React.RefObject<boolean>;
}) {
  const [value, setValue] = React.useState({ title: course.title, description: course.description });
  const tooShort = value.title.trim().length < 3;
  const autosave = useAutosave(value, (v) => mut.updateCourse.mutateAsync({ title: v.title.trim(), description: v.description }), {
    enabled: !tooShort,
  });

  // Rời trang/đóng trình soạn: lưu ngay phần đang chờ (hook chỉ dọn timer). Tên quá ngắn thì không lưu.
  const flushRef = React.useRef(autosave.flush);
  const tooShortRef = React.useRef(tooShort);
  React.useEffect(() => {
    flushRef.current = autosave.flush;
    tooShortRef.current = tooShort;
  });
  React.useEffect(
    () => () => {
      if (!tooShortRef.current && !deleted.current) void flushRef.current();
    },
    [deleted],
  );

  return (
    <section aria-labelledby="info-title" className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 id="info-title" className="text-lg font-semibold">
          Thông tin khóa học
        </h2>
        <span aria-live="polite" className="text-xs text-muted-foreground">
          {autosaveLabel(autosave.state)}
        </span>
      </div>
      <Field id="c-title" label="Tên khóa học" error={tooShort ? "Ít nhất 3 ký tự" : undefined}>
        <Input value={value.title} maxLength={200} onChange={(e) => setValue((v) => ({ ...v, title: e.target.value }))} />
      </Field>
      <Field id="c-desc" label="Mô tả (markdown)">
        <Textarea
          rows={6}
          maxLength={5000}
          value={value.description}
          onChange={(e) => setValue((v) => ({ ...v, description: e.target.value }))}
        />
      </Field>
    </section>
  );
}
