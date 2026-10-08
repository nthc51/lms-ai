"use client";

import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type AdminUser, fmtDate, useAdminActionsMutations } from "@/lib/admin-queries";
import { ReasonDialog } from "./reason-dialog";

const ROLE = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

export function UserStatus({ user }: { user: AdminUser }) {
  if (user.locked_at) return <Badge tone="destructive">Đã khóa</Badge>;
  if (!user.email_verified) return <Badge>Chưa xác nhận email</Badge>;
  if (user.role !== "teacher") return <Badge>Hoạt động</Badge>;
  if (user.teacher_status === "pending") return <Badge tone="accent">Chờ duyệt</Badge>;
  if (user.teacher_status === "rejected") return <Badge tone="destructive">Bị từ chối</Badge>;
  return <Badge tone="success">Đã duyệt</Badge>;
}


/** Bảng người dùng + thao tác theo trạng thái. Điện thoại cuộn ngang trong khung (bàn phím cũng cuộn được). */
export function UserTable({ users, caption }: { users: AdminUser[]; caption: string }) {
  const mut = useAdminActionsMutations();
  // Giữ người dùng đang thao tác cả khi hộp thoại đang đóng (tiêu đề không bị trống lúc chạy hiệu ứng đóng).
  const [target, setTarget] = React.useState<AdminUser | null>(null);
  const [dialog, setDialog] = React.useState<"reject" | "lock" | null>(null);
  const open = (kind: "reject" | "lock", u: AdminUser) => {
    setTarget(u);
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
      <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label={caption}>
        <table className="w-full min-w-[720px] text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="border-b text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Người dùng</th>
              <th className="px-4 py-2 font-medium">Vai trò</th>
              <th className="px-4 py-2 font-medium">Trạng thái</th>
              <th className="px-4 py-2 font-medium">Ngày tạo</th>
              <th className="px-4 py-2 font-medium">Khóa / Đăng ký</th>
              <th className="px-4 py-2 text-right font-medium">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.map((u) => (
              <tr key={u.id} className="align-top">
                <td className="px-4 py-3">
                  <p className="font-medium">{u.full_name}</p>
                  <p className="text-muted-foreground">{u.email}</p>
                  {u.review_note ? <p className="mt-1 text-xs text-muted-foreground">Lý do: {u.review_note}</p> : null}
                </td>
                <td className="px-4 py-3">{ROLE[u.role]}</td>
                <td className="px-4 py-3">
                  <UserStatus user={u} />
                </td>
                <td className="px-4 py-3 tabular-nums">{fmtDate(u.created_at)}</td>
                <td className="px-4 py-3 tabular-nums">
                  {u.role === "teacher" ? `${u.course_count} khóa` : u.role === "student" ? `${u.enrollment_count} đăng ký` : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    {u.role === "teacher" && u.teacher_status !== "approved" && !u.locked_at ? (
                      <Button size="sm" aria-label={`Duyệt ${u.full_name}`} onClick={() => run(mut.approve.mutateAsync(u.id), `Đã duyệt ${u.full_name}`).catch(() => {})}>
                        Duyệt
                      </Button>
                    ) : null}
                    {u.role === "teacher" && u.teacher_status === "pending" && !u.locked_at ? (
                      <Button size="sm" variant="destructive-outline" aria-label={`Từ chối ${u.full_name}`} onClick={() => open("reject", u)}>
                        Từ chối
                      </Button>
                    ) : null}
                    {u.role === "admin" ? null : u.locked_at ? (
                      <Button size="sm" variant="outline" aria-label={`Mở khóa ${u.full_name}`} onClick={() => run(mut.unlock.mutateAsync(u.id), `Đã mở khóa ${u.full_name}`).catch(() => {})}>
                        Mở khóa
                      </Button>
                    ) : (
                      <Button size="sm" variant="ghost" aria-label={`Khóa tài khoản ${u.full_name}`} onClick={() => open("lock", u)}>
                        Khóa
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ReasonDialog
        open={dialog === "reject"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Từ chối ${target?.full_name ?? ""}?`}
        description="Giảng viên sẽ không tạo được khóa học. Bạn vẫn có thể duyệt lại sau."
        confirmLabel="Từ chối"
        onSubmit={(reason) => run(mut.reject.mutateAsync({ id: target!.id, reason }), "Đã từ chối")}
      />
      <ReasonDialog
        open={dialog === "lock"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Khóa tài khoản ${target?.full_name ?? ""}?`}
        description="Người dùng bị đăng xuất khỏi mọi thiết bị và không đăng nhập được cho tới khi mở khóa."
        confirmLabel="Khóa tài khoản"
        required={false}
        onSubmit={(reason) => run(mut.lock.mutateAsync({ id: target!.id, reason }), "Đã khóa tài khoản")}
      />
    </>
  );
}
