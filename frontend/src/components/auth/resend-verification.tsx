"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { resendErrorMessage, useResendVerification } from "@/lib/auth/email-verification";

/** Nút "Gửi lại email xác nhận" có thông báo kết quả ngay bên dưới (role=status để trình đọc màn hình đọc). */
export function ResendVerification({ email, variant = "outline" }: { email: string; variant?: "outline" | "link" }) {
  const resend = useResendVerification();
  const [message, setMessage] = React.useState<{ ok: boolean; text: string } | null>(null);

  async function send() {
    setMessage(null);
    try {
      await resend.mutateAsync(email);
      setMessage({ ok: true, text: `Đã gửi lại. Kiểm tra hộp thư ${email} (cả mục Spam).` });
    } catch (err) {
      setMessage({ ok: false, text: resendErrorMessage(err) });
    }
  }

  return (
    <div className="space-y-2">
      <Button type="button" variant={variant} className={variant === "outline" ? "w-full" : undefined} onClick={send} loading={resend.isPending} loadingText="Đang gửi…">
        Gửi lại email xác nhận
      </Button>
      <p role="status" className={message ? (message.ok ? "text-sm text-muted-foreground" : "text-sm text-destructive") : "sr-only"}>
        {message?.text ?? ""}
      </p>
    </div>
  );
}
