"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNext } from "@/lib/auth/safe-next";

const schema = z.object({
  email: z.email("Email không hợp lệ"),
  password: z.string().min(1, "Nhập mật khẩu"),
});
type Values = z.infer<typeof schema>;

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: Values) {
    try {
      const user = await login(values.email, values.password);
      const fallback = user.role === "student" ? "/" : user.role === "admin" ? "/admin" : "/teach";
      router.replace(safeNext(params.get("next"), fallback));
    } catch (err) {
      // sai mật khẩu: báo ngay dưới ô mật khẩu và đưa con trỏ về đó (design-system §5.3)
      const msg = err instanceof ApiError && err.status === 401 ? "Email hoặc mật khẩu không đúng" : errorMessage(err);
      form.setError("password", { message: msg }, { shouldFocus: true });
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Đăng nhập</h1>
      <p className="mt-1 text-sm text-muted-foreground">Tiếp tục buổi học của bạn.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Field id="password" label="Mật khẩu" error={errors.password?.message}>
          <Input type="password" autoComplete="current-password" {...form.register("password")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting} loadingText="Đang đăng nhập…">
          Đăng nhập
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Chưa có tài khoản?{" "}
        <Link href={`/register${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`} className="font-medium text-primary underline underline-offset-4">
          Đăng ký
        </Link>
      </p>
    </>
  );
}
