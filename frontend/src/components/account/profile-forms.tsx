"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { type User, useAuth } from "@/lib/auth/auth-context";
import { passwordErrorField, passwordErrorMessage, useChangePassword, useUpdateProfile } from "@/lib/auth/profile";

const nameSchema = z.object({
  full_name: z
    .string()
    .transform((v) => v.trim().replace(/\s+/g, " "))
    .pipe(z.string().min(1, "Nhập họ tên").max(120, "Họ tên tối đa 120 ký tự")),
});
type NameIn = z.input<typeof nameSchema>;
type NameOut = z.output<typeof nameSchema>;

/** Sửa họ tên. Email là tên đăng nhập nên chỉ hiển thị. */
export function ProfileForm({ user }: { user: User }) {
  const { reloadUser } = useAuth();
  const update = useUpdateProfile();
  const form = useForm<NameIn, unknown, NameOut>({
    resolver: zodResolver(nameSchema),
    defaultValues: { full_name: user.full_name },
  });
  const { errors, isDirty } = form.formState;

  async function onSubmit({ full_name }: NameOut) {
    try {
      const saved = await update.mutateAsync(full_name);
      await reloadUser(); // menu tài khoản ở mọi trang đọc tên từ đây
      form.reset({ full_name: saved.full_name });
      toast.success("Đã lưu họ tên");
    } catch (err) {
      const msg = err instanceof ApiError ? (err.fieldError("full_name") ?? errorMessage(err)) : errorMessage(err);
      form.setError("full_name", { message: msg }, { shouldFocus: true });
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate aria-labelledby="h-profile">
      <h2 id="h-profile" className="text-lg font-semibold">
        Thông tin cá nhân
      </h2>
      <div className="space-y-1.5">
        <p className="text-sm font-medium">Email</p>
        <p className="text-sm text-muted-foreground">{user.email} (dùng để đăng nhập, không đổi được)</p>
      </div>
      <Field id="full_name" label="Họ tên" error={errors.full_name?.message}>
        <Input autoComplete="name" {...form.register("full_name")} />
      </Field>
      <Button type="submit" disabled={!isDirty} loading={update.isPending} loadingText="Đang lưu…">
        Lưu họ tên
      </Button>
    </form>
  );
}

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Nhập mật khẩu hiện tại"),
    new_password: z.string().min(8, "Mật khẩu mới ít nhất 8 ký tự").max(128, "Mật khẩu tối đa 128 ký tự"),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Hai mật khẩu chưa khớp" });
type PasswordValues = z.infer<typeof passwordSchema>;

const EMPTY: PasswordValues = { current_password: "", new_password: "", confirm: "" };

/** Đổi mật khẩu: phiên trên trình duyệt này được giữ, các thiết bị khác bị đăng xuất. */
export function PasswordForm() {
  const change = useChangePassword();
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<PasswordValues>({ resolver: zodResolver(passwordSchema), defaultValues: EMPTY });
  const { errors } = form.formState;

  async function onSubmit({ current_password, new_password }: PasswordValues) {
    setFormError(null);
    try {
      await change.mutateAsync({ current_password, new_password });
      form.reset(EMPTY);
      toast.success("Đã đổi mật khẩu. Các thiết bị khác sẽ phải đăng nhập lại.");
    } catch (err) {
      const field = passwordErrorField(err);
      if (field === "current") form.setError("current_password", { message: errorMessage(err) }, { shouldFocus: true });
      else if (field === "new") form.setError("new_password", { message: errorMessage(err) }, { shouldFocus: true });
      else setFormError(passwordErrorMessage(err));
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate aria-labelledby="h-password">
      <h2 id="h-password" className="text-lg font-semibold">
        Đổi mật khẩu
      </h2>
      <Field id="current_password" label="Mật khẩu hiện tại" error={errors.current_password?.message}>
        <Input type="password" autoComplete="current-password" {...form.register("current_password")} />
      </Field>
      <Field id="new_password" label="Mật khẩu mới" error={errors.new_password?.message} hint="Ít nhất 8 ký tự">
        <Input type="password" autoComplete="new-password" {...form.register("new_password")} />
      </Field>
      <Field id="confirm" label="Nhập lại mật khẩu mới" error={errors.confirm?.message}>
        <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
      </Field>
      {formError ? (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      ) : null}
      <Button type="submit" loading={change.isPending} loadingText="Đang đổi…">
        Đổi mật khẩu
      </Button>
    </form>
  );
}
