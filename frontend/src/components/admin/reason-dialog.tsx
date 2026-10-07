"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/input";

/**
 * Hộp thoại nhập lý do cho thao tác quản trị. Lý do sẽ hiện cho chính người bị ảnh hưởng
 * (giảng viên bị từ chối, chủ khóa bị ẩn), nên viết rõ ràng, lịch sự.
 * `onSubmit` ném lỗi thì hộp thoại giữ nguyên để sửa (nơi gọi tự báo toast).
 */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  required = true,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  required?: boolean;
  onSubmit: (reason: string) => Promise<unknown>;
}) {
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string>();
  const [pending, setPending] = React.useState(false);

  function change(o: boolean) {
    if (!o) {
      setReason("");
      setError(undefined);
    }
    onOpenChange(o);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (required && !reason.trim()) return setError("Cần nhập lý do");
    setPending(true);
    try {
      await onSubmit(reason.trim());
      change(false);
    } catch {
      // giữ hộp thoại mở
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent title={title} description={description}>
        <form onSubmit={submit} className="space-y-4" noValidate>
          <Field id="admin-reason" label={required ? "Lý do" : "Lý do (không bắt buộc)"} error={error} hint="Người dùng sẽ thấy lý do này.">
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={500} autoFocus />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => change(false)}>
              Hủy
            </Button>
            <Button type="submit" variant="destructive" loading={pending} loadingText="Đang xử lý…">
              {confirmLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
