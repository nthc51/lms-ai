"use client";

import { MailCheck } from "lucide-react";
import Link from "next/link";
import { ResendVerification } from "./resend-verification";

/** Màn sau khi đăng ký: chưa đăng nhập được cho tới khi bấm link trong email. */
export function CheckEmail({ email, teacher }: { email: string; teacher: boolean }) {
  return (
    <div className="text-center">
      <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
      <h1 className="mt-3 text-2xl font-semibold">Kiểm tra hộp thư của bạn</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Chúng tôi đã gửi link xác nhận tới <span className="font-medium text-foreground">{email}</span>. Bấm link trong
        email để kích hoạt tài khoản (link có hiệu lực 24 giờ).
      </p>
      {teacher ? (
        <p className="mt-2 text-sm text-muted-foreground">Sau khi xác nhận email, tài khoản giảng viên sẽ chờ quản trị viên duyệt.</p>
      ) : null}
      <div className="mt-6 text-left">
        <p className="mb-2 text-sm text-muted-foreground">Không thấy email? Xem trong mục Spam, hoặc:</p>
        <ResendVerification email={email} />
      </div>
      <p className="mt-6 text-sm text-muted-foreground">
        Đã xác nhận?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">
          Đăng nhập
        </Link>
      </p>
    </div>
  );
}
