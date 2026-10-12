"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { forgotErrorMessage, useForgotPassword } from "@/lib/auth/password-reset";

const schema = z.object({ email: z.email("Email không hợp lệ") });
type Values = z.infer<typeof schema>;

export function ForgotPasswordForm() {
  const params = useSearchParams();
  const forgot = useForgotPassword();
  const [sentTo, setSentTo] = React.useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: params.get("email") ?? "" } });
  const { errors } = form.formState;
  const heading = React.useRef<HTMLHeadingElement>(null);
  React.useEffect(() => {
    if (sentTo) heading.current?.focus();
  }, [sentTo]);

  async function onSubmit(values: Values) {
    const email = values.email.trim().toLowerCase();
    try {
      await forgot.mutateAsync(email);
      setSentTo(email);
    } catch (err) {
      form.setError("email", { message: forgotErrorMessage(err) }, { shouldFocus: true });
    }
  }

  if (sentTo)
    return (
      <div className="text-center">
        <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
        <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
          Kiểm tra hộp thư
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Nếu {sentTo} đã đăng ký, chúng tôi vừa gửi link đặt lại mật khẩu (hiệu lực 60 phút). Xem cả mục Spam.
        </p>
        <Button variant="outline" className="mt-6 w-full" onClick={() => setSentTo(null)}>
          Gửi lại hoặc dùng email khác
        </Button>
        <p className="mt-4 text-sm">
          <Link href="/login" className="font-medium text-primary underline underline-offset-4">
            Quay lại đăng nhập
          </Link>
        </p>
      </div>
    );

  return (
    <>
      <h1 className="text-2xl font-semibold">Quên mật khẩu</h1>
      <p className="mt-1 text-sm text-muted-foreground">Nhập email đã đăng ký, chúng tôi sẽ gửi link để đặt mật khẩu mới.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={forgot.isPending} loadingText="Đang gửi…">
          Gửi link đặt lại mật khẩu
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Nhớ ra rồi?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">
          Đăng nhập
        </Link>
      </p>
    </>
  );
}
