"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNext } from "@/lib/auth/safe-next";
import { cn } from "@/lib/utils";

const schema = z.object({
  full_name: z.string().trim().min(1, "Nhập họ tên").max(120),
  email: z.email("Email không hợp lệ"),
  password: z.string().min(8, "Mật khẩu ít nhất 8 ký tự").max(128),
  role: z.enum(["student", "teacher"]),
});
type Values = z.infer<typeof schema>;

export function RegisterForm() {
  const { register: signup, login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", password: "", role: "student" },
  });
  const { errors, isSubmitting } = form.formState;
  const role = useWatch({ control: form.control, name: "role" });

  async function onSubmit(values: Values) {
    try {
      await signup(values);
      const user = await login(values.email, values.password);
      if (user.role === "teacher") toast("Tài khoản giảng viên cần quản trị viên duyệt trước khi tạo khóa học.");
      router.replace(safeNext(params.get("next"), user.role === "student" ? "/explore" : "/teach"));
    } catch (err) {
      if (err instanceof ApiError && err.code === "EMAIL_TAKEN") {
        form.setError("email", { message: err.message }, { shouldFocus: true });
      } else {
        form.setError("root", { message: errorMessage(err) });
      }
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Tạo tài khoản</h1>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Bạn là</legend>
          <div role="radiogroup" className="grid grid-cols-2 gap-2">
            {(["student", "teacher"] as const).map((r) => (
              <label
                key={r}
                className={cn(
                  "flex h-11 cursor-pointer items-center justify-center rounded-md border text-sm",
                  role === r && "border-primary bg-primary/10 font-medium text-primary",
                )}
              >
                <input type="radio" value={r} className="sr-only" {...form.register("role")} />
                {r === "student" ? "Học viên" : "Giảng viên"}
              </label>
            ))}
          </div>
        </fieldset>
        <Field id="full_name" label="Họ và tên" error={errors.full_name?.message}>
          <Input autoComplete="name" {...form.register("full_name")} />
        </Field>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Field id="password" label="Mật khẩu" error={errors.password?.message} hint="Ít nhất 8 ký tự">
          <Input type="password" autoComplete="new-password" {...form.register("password")} />
        </Field>
        {errors.root ? (
          <p role="alert" className="text-sm text-destructive">
            {errors.root.message}
          </p>
        ) : null}
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting} loadingText="Đang tạo tài khoản…">
          Tạo tài khoản
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Đã có tài khoản?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">
          Đăng nhập
        </Link>
      </p>
    </>
  );
}
