import { Suspense } from "react";
import { ForgotPasswordForm } from "./forgot-password-form";

export const metadata = { title: "Quên mật khẩu" };

export default function ForgotPasswordPage() {
  return (
    <Suspense>
      <ForgotPasswordForm />
    </Suspense>
  );
}
