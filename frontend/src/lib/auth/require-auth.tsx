"use client";

import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { Skeleton } from "@/components/ui/misc";
import { isStaff, useAuth } from "./auth-context";

/** Chặn trang cần đăng nhập. Chưa đăng nhập → /login?next=<trang hiện tại>. */
export function RequireAuth({ staff = false, children }: { staff?: boolean; children: React.ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return (
      <div className="space-y-3 p-6" aria-busy="true" aria-label="Đang tải">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (staff && !isStaff(user)) {
    return (
      <div className="mx-auto max-w-md p-6 text-center">
        <h1 className="text-xl font-semibold">Bạn chưa có quyền giảng dạy</h1>
        <p className="mt-2 text-muted-foreground">
          {user?.role === "teacher"
            ? "Tài khoản giảng viên của bạn đang chờ quản trị viên duyệt."
            : "Trang này chỉ dành cho giảng viên."}
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
