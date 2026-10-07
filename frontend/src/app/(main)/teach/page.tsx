"use client";

import { GraduationCap, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { RequireAuth } from "@/lib/auth/require-auth";
import { useCreateCourse, useTeacherCourses } from "@/lib/teach-queries";

export default function TeachPage() {
  return (
    <RequireAuth staff>
      <TeachGate />
    </RequireAuth>
  );
}

/** API danh sách/tạo khóa chỉ dành cho giảng viên; quản trị viên vào trình soạn từng khóa qua /teach/[slug]. */
function TeachGate() {
  const { user } = useAuth();
  if (user?.role === "admin")
    return (
      <>
        <PageHeader title="Khóa đang dạy" />
        <div className="rounded-lg border p-6 text-center">
          <p className="text-muted-foreground">Trang này dành cho giảng viên. Quản trị viên xem mọi khóa học ở khu quản trị.</p>
          <Button asChild variant="outline" className="mt-4">
            <Link href="/admin/courses">Đến danh sách khóa học</Link>
          </Button>
        </div>
      </>
    );
  return <TeacherCourses />;
}

function TeacherCourses() {
  const courses = useTeacherCourses();
  const [open, setOpen] = React.useState(false);
  const create = (
    <Button onClick={() => setOpen(true)}>
      <Plus /> Tạo khóa học
    </Button>
  );

  return (
    <>
      <PageHeader title="Khóa đang dạy" actions={courses.data?.items.length ? create : null} />
      {courses.isPending ? (
        <CardListSkeleton count={3} />
      ) : courses.isError ? (
        <ErrorState error={courses.error} onRetry={() => courses.refetch()} />
      ) : courses.data.items.length === 0 ? (
        <EmptyState icon={GraduationCap} title="Bạn chưa có khóa học nào." action={create} />
      ) : (
        <ul className="divide-y rounded-lg border bg-surface">
          {courses.data.items.map((c) => (
            <li key={c.id}>
              <Link href={`/teach/${c.slug}`} className="flex items-center justify-between gap-3 px-4 py-4 hover:bg-muted">
                <span className="font-medium">{c.title}</span>
                {c.hidden_reason ? (
                  <Badge tone="destructive">Đã bị ẩn</Badge>
                ) : c.status === "published" ? (
                  <Badge tone="success">Đã xuất bản</Badge>
                ) : (
                  <Badge>Nháp</Badge>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
      <CreateCourseDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

function CreateCourseDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [error, setError] = React.useState<string>();
  const createCourse = useCreateCourse();
  const pending = createCourse.isPending;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (title.trim().length < 3) return setError("Tên khóa học ít nhất 3 ký tự");
    try {
      const c = await createCourse.mutateAsync({ title: title.trim(), description });
      router.push(`/teach/${c.slug}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Tạo khóa học" description="Bạn có thể sửa tên và mô tả sau. Khóa học ở dạng nháp cho tới khi xuất bản.">
        <form onSubmit={submit} className="space-y-4">
          <Field id="course-title" label="Tên khóa học" error={error}>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} autoFocus />
          </Field>
          <Field id="course-desc" label="Mô tả ngắn (markdown)">
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} maxLength={5000} />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" loading={pending} loadingText="Đang tạo…">
              Tạo và mở trình soạn
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
