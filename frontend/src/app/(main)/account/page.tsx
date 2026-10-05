"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/app/states";
import { ThemeSwitcher } from "@/components/app/theme-switcher";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";
import { RequireAuth } from "@/lib/auth/require-auth";

const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

/** Trang tài khoản (chủ yếu cho điện thoại, nơi không có menu góc trên). */
export default function AccountPage() {
  const { user, logout } = useAuth();
  const router = useRouter();
  return (
    <RequireAuth>
      <PageHeader title="Tài khoản" />
      {user ? (
        <div className="max-w-md space-y-8">
          <div>
            <p className="font-medium">{user.full_name}</p>
            <p className="text-sm text-muted-foreground">
              {user.email} · {ROLE_LABEL[user.role]}
            </p>
          </div>
          <div>
            <h2 className="mb-2 text-sm font-medium">Chế độ màu</h2>
            <ThemeSwitcher />
          </div>
          <Button
            variant="outline"
            onClick={async () => {
              await logout();
              router.push("/");
            }}
          >
            <LogOut /> Đăng xuất
          </Button>
        </div>
      ) : null}
    </RequireAuth>
  );
}
