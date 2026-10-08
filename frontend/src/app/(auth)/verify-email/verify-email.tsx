"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { resendErrorMessage, useResendVerification, useVerifyEmail } from "@/lib/auth/email-verification";

export function VerifyEmail() {
  const token = useSearchParams().get("token");
  const verify = useVerifyEmail(token);

  if (token && verify.isPending)
    return (
      <div aria-busy="true" aria-label="Đang xác nhận email" className="space-y-3">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-16 w-full" />
      </div>
    );

  if (verify.isSuccess) {
    const teacherWaiting = verify.data.role === "teacher" && verify.data.teacher_status === "pending";
    return (
      <div className="text-center">
        <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
        <h1 className="mt-3 text-2xl font-semibold">Email đã được xác nhận</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {teacherWaiting
            ? "Bạn đã đăng nhập được. Tài khoản giảng viên đang chờ quản trị viên duyệt, bạn sẽ nhận email khi có kết quả."
            : "Tài khoản đã được kích hoạt. Bạn có thể đăng nhập ngay."}
        </p>
        <Button asChild size="lg" className="mt-6 w-full">
          <Link href="/login">Đăng nhập</Link>
        </Button>
      </div>
    );
  }

  const expired = verify.error instanceof ApiError && verify.error.code === "TOKEN_EXPIRED";
  return (
    <div>
      <XCircle className="mx-auto size-10 text-destructive" aria-hidden />
      <h1 className="mt-3 text-center text-2xl font-semibold">{expired ? "Link đã hết hạn" : "Link không dùng được"}</h1>
      <p className="mt-2 text-center text-sm text-muted-foreground">
        {token ? errorMessage(verify.error) : "Thiếu mã xác nhận trong link."} Nhập email để nhận link mới.
      </p>
      <ResendForm />
    </div>
  );
}

function ResendForm() {
  const resend = useResendVerification();
  const [email, setEmail] = React.useState("");
  const [message, setMessage] = React.useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = email.trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(value)) return setMessage({ ok: false, text: "Email không hợp lệ" });
    try {
      await resend.mutateAsync(value);
      setMessage({ ok: true, text: `Nếu ${value} đã đăng ký và chưa xác nhận, link mới đã được gửi tới hộp thư.` });
    } catch (err) {
      setMessage({ ok: false, text: resendErrorMessage(err) });
    }
  }

  return (
    <form className="mt-6 space-y-3" onSubmit={submit} noValidate>
      <Field id="resend-email" label="Email đã đăng ký">
        <Input type="email" autoComplete="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Button type="submit" variant="outline" className="w-full" loading={resend.isPending} loadingText="Đang gửi…">
        Gửi link xác nhận mới
      </Button>
      <p role="status" className={message ? (message.ok ? "text-sm text-muted-foreground" : "text-sm text-destructive") : "sr-only"}>
        {message?.text ?? ""}
      </p>
    </form>
  );
}
