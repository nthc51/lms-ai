"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type AdminCourse, fmtDate, useAdminActionsMutations } from "@/lib/admin-queries";
import { ReasonDialog } from "./reason-dialog";

export function CourseStatusBadge({ course }: { course: Pick<AdminCourse, "status" | "hidden_at"> }) {
  if (course.hidden_at) return <Badge tone="destructive">Đã ẩn</Badge>;
  if (course.status === "published") return <Badge tone="success">Đã xuất bản</Badge>;
  if (course.status === "archived") return <Badge>Lưu trữ</Badge>;
  return <Badge>Nháp</Badge>;
}

export function CourseTable({ courses }: { courses: AdminCourse[] }) {
  const mut = useAdminActionsMutations();
  const [target, setTarget] = React.useState<AdminCourse | null>(null);
  const [dialog, setDialog] = React.useState<"hide" | "unhide" | null>(null);
  const open = (kind: "hide" | "unhide", c: AdminCourse) => {
    setTarget(c);
    setDialog(kind);
  };

  async function run(p: Promise<unknown>, ok: string) {
    try {
      await p;
      toast.success(ok);
    } catch (err) {
      toast.error(errorMessage(err));
      throw err;
    }
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng khóa học">
        <table className="w-full min-w-[760px] text-sm">
          <caption className="sr-only">Bảng khóa học</caption>
          <thead className="border-b text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Khóa học</th>
              <th className="px-4 py-2 font-medium">Giảng viên</th>
              <th className="px-4 py-2 font-medium">Trạng thái</th>
              <th className="px-4 py-2 font-medium">Bài / Học viên</th>
              <th className="px-4 py-2 font-medium">Ngày tạo</th>
              <th className="px-4 py-2 text-right font-medium">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {courses.map((c) => (
              <tr key={c.id} className="align-top">
                <td className="px-4 py-3">
                  {/* Admin được xem cả khóa nháp/đã ẩn (backend coi admin như chủ khóa) */}
                  <Link href={`/courses/${c.slug}`} className="font-medium text-primary hover:underline">
                    {c.title}
                  </Link>
                  {c.hidden_reason ? <p className="mt-1 text-xs text-muted-foreground">Lý do ẩn: {c.hidden_reason}</p> : null}
                </td>
                <td className="px-4 py-3">
                  <p>{c.teacher_name}</p>
                  <p className="text-muted-foreground">{c.teacher_email}</p>
                </td>
                <td className="px-4 py-3">
                  <CourseStatusBadge course={c} />
                </td>
                <td className="px-4 py-3 tabular-nums">
                  {c.lesson_count} / {c.enrollment_count}
                </td>
                <td className="px-4 py-3 tabular-nums">{fmtDate(c.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    {c.hidden_at ? (
                      <Button size="sm" variant="outline" aria-label={`Hiện lại ${c.title}`} onClick={() => open("unhide", c)}>
                        Hiện lại
                      </Button>
                    ) : c.status === "published" ? (
                      <Button size="sm" variant="destructive-outline" aria-label={`Ẩn ${c.title}`} onClick={() => open("hide", c)}>
                        Ẩn
                      </Button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ReasonDialog
        open={dialog === "hide"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Ẩn khóa “${target?.title ?? ""}”?`}
        description={`Khóa biến mất khỏi trang Khám phá và ${target?.enrollment_count ?? 0} học viên đã đăng ký tạm thời không vào học được. Giảng viên không tự xuất bản lại được.`}
        confirmLabel="Ẩn khóa học"
        onSubmit={(reason) => run(mut.hide.mutateAsync({ id: target!.id, reason }), "Đã ẩn khóa học")}
      />
      <ConfirmDialog
        open={dialog === "unhide"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Hiện lại khóa “${target?.title ?? ""}”?`}
        description="Khóa xuất hiện lại trên trang Khám phá và học viên đã đăng ký học tiếp được."
        confirmLabel="Hiện lại"
        pendingLabel="Đang xử lý…"
        onConfirm={() => run(mut.unhide.mutateAsync(target!.id), "Đã hiện lại khóa học")}
      />
    </>
  );
}
