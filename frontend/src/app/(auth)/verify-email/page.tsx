import { Suspense } from "react";
import { VerifyEmail } from "./verify-email";

export const metadata = { title: "Xác nhận email" };

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmail />
    </Suspense>
  );
}
