"use client";

import { LogIn, LogOut, NotebookPen, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";
import { ThemeSwitcher } from "./theme-switcher";

export const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

/** Chữ cái đại diện: chữ đầu của tên gọi (chữ cuối họ tên Việt), "Nguyễn Văn An" → "A". */
export function initialOf(fullName: string) {
  const given = fullName.trim().split(/\s+/).pop() ?? "";
  return (given[0] ?? "?").toLocaleUpperCase("vi");
}

/** Đăng xuất rồi nạp lại trang chủ. Tải lại hẳn (không router.push) để trang đang chặn bằng RequireAuth
 *  không kịp chuyển sang /login?next=…, và mọi dữ liệu của phiên cũ trong bộ nhớ đều bị bỏ. */
export async function logoutAndGoHome(logout: () => Promise<void>) {
  await logout();
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- cố ý tải lại hẳn trang (xem chú thích trên)
  window.location.assign("/");
}

/**
 * Nút tài khoản ở góc trên, dùng ở mọi khung trang (AppShell, trang học, quiz).
 * `compact`: chỉ hiện chữ cái đại diện (tên vẫn có cho trình đọc màn hình).
 * Trên điện thoại luôn ở dạng gọn.
 */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, status, logout } = useAuth();
  const router = useRouter();

  if (status === "loading") return <div className="size-10 shrink-0" aria-hidden />;
  if (!user)
    return (
      <Button asChild variant="outline" size={compact ? "sm" : "default"}>
        <Link href="/login">
          <LogIn /> Đăng nhập
        </Link>
      </Button>
    );

  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" className="shrink-0 gap-2 px-1.5 md:px-2">
          <span
            className="grid size-8 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
            aria-hidden
          >
            {initialOf(user.full_name)}
          </span>
          <span className={cn("max-w-40 truncate", compact ? "sr-only" : "sr-only md:not-sr-only")}>
            {user.full_name}
          </span>
        </Button>
      </MenuTrigger>
      <MenuContent>
        <div className="px-2 py-2">
          <p className="truncate text-sm font-medium">{user.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {user.email} · {ROLE_LABEL[user.role]}
          </p>
        </div>
        <MenuSeparator />
        <MenuItem onSelect={() => router.push("/account")}>
          <UserRound /> Hồ sơ cá nhân
        </MenuItem>
        {user.role !== "admin" ? (
          <MenuItem onSelect={() => router.push("/notes")}>
            <NotebookPen /> Ghi chú của tôi
          </MenuItem>
        ) : null}
        <div className="px-2 py-2">
          <ThemeSwitcher compact />
        </div>
        <MenuSeparator />
        <MenuItem onSelect={() => void logoutAndGoHome(logout)}>
          <LogOut /> Đăng xuất
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}
