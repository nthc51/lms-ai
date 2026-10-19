"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";
import { isActive, navItems } from "./nav-items";
import { NotificationBell } from "./notification-bell";
import { UserMenu } from "./user-menu";

/**
 * Khung chung (cùng ngôn ngữ với trang chủ cho khách): ô tên app nền đậm, thanh bên một tông màu riêng không viền,
 * mục đang chọn là nền thẻ + vạch màu chính bên trái. Thanh bên 240px (≥1024px), thu gọn icon 64px (768–1023px),
 * thanh dưới tối đa 3 mục (<768px; tài khoản nằm ở menu góc trên). Góc trên luôn có menu tài khoản (hồ sơ, ghi chú, chế độ màu, đăng xuất).
 * Trang bài học và quiz không dùng khung này nhưng có cùng menu tài khoản ở thanh trên.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, status } = useAuth();
  const pathname = usePathname();
  const items = navItems(user);

  // Trang chủ của khách là trang giới thiệu toàn màn hình, có thanh điều hướng riêng.
  // Lúc đang khôi phục phiên cũng chưa vẽ khung, để khách không thấy khung app nháy lên rồi biến mất.
  if (pathname === "/" && status !== "authenticated") return <>{children}</>;

  return (
    <div className="min-h-dvh md:pl-16 lg:pl-60">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        Bỏ qua tới nội dung
      </a>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-16 flex-col bg-sidebar md:flex lg:w-60">
        <Link
          href="/"
          aria-label="LMS-AI, trang chủ"
          className="flex h-16 shrink-0 items-center justify-center bg-brand text-xl font-extrabold tracking-[-0.04em] text-white lg:justify-start lg:px-6"
        >
          <span className="lg:hidden" aria-hidden>
            L
          </span>
          <span className="hidden lg:inline">LMS-AI</span>
        </Link>
        <nav aria-label="Điều hướng chính" className="flex flex-col gap-0.5 px-2 py-5 lg:px-3">
          {items.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              title={label}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={cn(
                "relative flex h-11 items-center justify-center gap-3 px-3 text-[15px] font-semibold text-muted-foreground transition-colors duration-150 hover:bg-field-3 hover:text-foreground lg:justify-start lg:px-3.5",
                isActive(pathname, href) &&
                  "bg-surface text-foreground before:absolute before:inset-y-2.5 before:left-0 before:w-1 before:bg-primary hover:bg-surface",
              )}
            >
              <Icon className="size-5 shrink-0" aria-hidden />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          ))}
        </nav>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-background px-4 md:h-16 md:px-8">
        <Link href="/" className="text-lg font-extrabold tracking-[-0.04em] md:hidden">
          LMS-AI
        </Link>
        <div className="hidden md:block" />
        <div className="flex items-center gap-1">
          <NotificationBell />
          <UserMenu />
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 pt-4 md:px-8 md:pb-16 md:pt-6">
        {children}
      </main>

      <nav
        aria-label="Điều hướng chính"
        className="fixed inset-x-0 bottom-0 z-30 grid h-16 bg-sidebar md:hidden"
        style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
      >
        {items.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={isActive(pathname, href) ? "page" : undefined}
            className={cn(
              "flex flex-col items-center justify-center gap-0.5 text-xs font-semibold",
              isActive(pathname, href) ? "bg-surface text-primary" : "text-muted-foreground",
            )}
          >
            <Icon className="size-5" aria-hidden />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
