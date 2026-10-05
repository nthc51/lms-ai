import { Suspense } from "react";
import { RegisterForm } from "./register-form";

export const metadata = { title: "Đăng ký" };

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterForm />
    </Suspense>
  );
}
