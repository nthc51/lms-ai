"use client";

import { LogOut, NotebookPen } from "lucide-react";
import Link from "next/link";
import { PasswordForm, ProfileForm } from "@/components/account/profile-forms";
import { PageHeader } from "@/components/app/states";
import { ThemeSwitcher } from "@/components/app/theme-switcher";
import { logoutAndGoHome, ROLE_LABEL } from "@/components/app/user-menu";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";
import { RequireAuth } from "@/lib/auth/require-auth";

/** Hồ sơ cá nhân: sửa họ tên, đổi mật khẩu, chế độ màu, đăng xuất. Mở từ menu tài khoản ở mọi trang. */
export default function AccountPage() {
  const { user, logout } = useAuth();
  return (
    <RequireAuth>
      <PageHeader title="Hồ sơ cá nhân">{user ? `${user.email} · ${ROLE_LABEL[user.role]}` : null}</PageHeader>
      {user ? (
        <div className="grid max-w-3xl gap-10 md:grid-cols-2">
          <ProfileForm key={user.id} user={user} />
          <PasswordForm />
          <section aria-labelledby="h-theme" className="space-y-3">
            <h2 id="h-theme" className="text-lg font-semibold">
              Chế độ màu
            </h2>
            <ThemeSwitcher />
          </section>
          <section aria-labelledby="h-session" className="space-y-3">
            <h2 id="h-session" className="text-lg font-semibold">
              Phiên đăng nhập
            </h2>
            <div className="flex flex-wrap gap-3">
              {user.role !== "admin" ? (
                <Button asChild variant="outline">
                  <Link href="/notes">
                    <NotebookPen /> Ghi chú của tôi
                  </Link>
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => void logoutAndGoHome(logout)}>
                <LogOut /> Đăng xuất
              </Button>
            </div>
          </section>
        </div>
      ) : null}
    </RequireAuth>
  );
}
