"use client";

import { LogIn, LogOut, User as UserIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";
import { isActive, navItems } from "./nav-items";
import { ThemeSwitcher } from "./theme-switcher";

const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

/**
 * Khung chung: thanh bên 240px (≥1024px), thu gọn icon 64px (768–1023px),
 * thanh dưới tối đa 4 mục (<768px). Trang bài học không dùng khung này.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const items = navItems(user);

  return (
    <div className="min-h-dvh md:pl-16 lg:pl-60">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        Bỏ qua tới nội dung
      </a>
      <aside className="fixed inset-y-0 left-0 hidden w-16 flex-col border-r bg-surface md:flex lg:w-60">
        <Link href="/" className="flex h-14 items-center gap-2 px-4 font-semibold">
          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">L</span>
          <span className="hidden lg:inline">LMS-AI</span>
        </Link>
        <nav aria-label="Điều hướng chính" className="flex flex-col gap-1 p-2">
          {items.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              title={label}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={cn(
                "flex h-10 items-center gap-3 rounded-md px-3 text-sm transition-colors duration-150 hover:bg-muted",
                isActive(pathname, href) && "bg-muted font-medium text-primary",
              )}
            >
              <Icon className="size-5 shrink-0" aria-hidden />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          ))}
        </nav>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur md:px-6">
        <Link href="/" className="font-semibold md:hidden">
          LMS-AI
        </Link>
        <div className="hidden md:block" />
        <AccountMenu />
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 md:px-8 md:pb-10 md:pt-8">
        {children}
      </main>

      <nav
        aria-label="Điều hướng chính"
        className="fixed inset-x-0 bottom-0 z-30 grid h-16 border-t bg-surface md:hidden"
        style={{ gridTemplateColumns: `repeat(${items.length + 1}, minmax(0, 1fr))` }}
      >
        {items.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={isActive(pathname, href) ? "page" : undefined}
            className={cn(
              "flex flex-col items-center justify-center gap-0.5 text-xs",
              isActive(pathname, href) ? "text-primary" : "text-muted-foreground",
            )}
          >
            <Icon className="size-5" aria-hidden />
            {label}
          </Link>
        ))}
        <Link
          href={user ? "/account" : "/login"}
          aria-current={isActive(pathname, "/account") ? "page" : undefined}
          className={cn(
            "flex flex-col items-center justify-center gap-0.5 text-xs",
            isActive(pathname, "/account") ? "text-primary" : "text-muted-foreground",
          )}
        >
          <UserIcon className="size-5" aria-hidden />
          {user ? "Tài khoản" : "Đăng nhập"}
        </Link>
      </nav>
    </div>
  );
}

function AccountMenu() {
  const { user, status, logout } = useAuth();
  const router = useRouter();
  if (status === "loading") return <div className="h-10 w-24" />;
  if (!user)
    return (
      <Button asChild variant="outline" className="hidden md:inline-flex">
        <Link href="/login">
          <LogIn /> Đăng nhập
        </Link>
      </Button>
    );
  return (
    <div className="hidden md:block">
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost">
            <span className="grid size-7 place-items-center rounded-full bg-muted text-xs font-semibold">
              {user.full_name.slice(0, 1).toUpperCase()}
            </span>
            {user.full_name}
          </Button>
        </MenuTrigger>
        <MenuContent>
          <div className="px-2 py-1.5 text-xs text-muted-foreground">
            {user.email} · {ROLE_LABEL[user.role]}
          </div>
          <div className="px-2 py-2">
            <ThemeSwitcher compact />
          </div>
          <MenuSeparator />
          <MenuItem
            onSelect={async () => {
              await logout();
              router.push("/");
            }}
          >
            <LogOut /> Đăng xuất
          </MenuItem>
        </MenuContent>
      </Menu>
    </div>
  );
}
