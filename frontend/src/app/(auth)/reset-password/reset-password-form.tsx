"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/errors";
import { isDeadResetLink, useResetPassword } from "@/lib/auth/password-reset";

const schema = z
  .object({
    password: z.string().min(8, "Mật khẩu ít nhất 8 ký tự").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Hai mật khẩu chưa khớp" });
type Values = z.infer<typeof schema>;

export function ResetPasswordForm() {
  const token = useSearchParams().get("token");
  const reset = useResetPassword();
  const [state, setState] = React.useState<"form" | "done" | "dead">(token ? "form" : "dead");
  const [deadMessage, setDeadMessage] = React.useState("Thiếu mã đặt lại trong link.");
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { password: "", confirm: "" } });
  const { errors } = form.formState;
  const heading = React.useRef<HTMLHeadingElement>(null);
  React.useEffect(() => {
    if (state !== "form") heading.current?.focus();
  }, [state]);

  async function onSubmit(values: Values) {
    try {
      await reset.mutateAsync({ token: token!, password: values.password });
      setState("done");
    } catch (err) {
      if (isDeadResetLink(err)) {
        setDeadMessage(errorMessage(err));
        setState("dead");
        return;
      }
      form.setError("password", { message: errorMessage(err) }, { shouldFocus: true });
    }
  }

  if (state === "done")
    return (
      <div className="text-center">
        <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
        <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
          Đã đặt mật khẩu mới
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Bạn đã được đăng xuất khỏi mọi thiết bị. Đăng nhập lại bằng mật khẩu mới.
        </p>
        <Button asChild size="lg" className="mt-6 w-full">
          <Link href="/login">Đăng nhập</Link>
        </Button>
      </div>
    );

  if (state === "dead")
    return (
      <div className="text-center">
        <XCircle className="mx-auto size-10 text-destructive" aria-hidden />
        <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
          Link không dùng được
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{deadMessage} Mỗi link chỉ dùng được một lần.</p>
        <Button asChild size="lg" className="mt-6 w-full">
          <Link href="/forgot-password">Gửi link mới</Link>
        </Button>
      </div>
    );

  return (
    <>
      <h1 className="text-2xl font-semibold">Đặt mật khẩu mới</h1>
      <p className="mt-1 text-sm text-muted-foreground">Sau khi đổi, mọi phiên đăng nhập cũ sẽ bị đăng xuất.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <Field id="password" label="Mật khẩu mới" error={errors.password?.message} hint="Ít nhất 8 ký tự">
          <Input type="password" autoComplete="new-password" {...form.register("password")} />
        </Field>
        <Field id="confirm" label="Nhập lại mật khẩu mới" error={errors.confirm?.message}>
          <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={reset.isPending} loadingText="Đang lưu…">
          Đặt mật khẩu mới
        </Button>
      </form>
    </>
  );
}
