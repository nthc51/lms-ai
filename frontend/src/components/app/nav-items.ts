import { BookMarked, Compass, GraduationCap, Home, type LucideIcon } from "lucide-react";
import type { User } from "@/lib/auth/auth-context";

export type NavItem = { href: string; label: string; icon: LucideIcon };

/** Mục điều hướng theo vai trò (design-system §7.1). Điện thoại hiển thị tối đa 4 mục. */
export function navItems(user: User | null): NavItem[] {
  const base: NavItem[] = [
    { href: "/", label: "Trang chủ", icon: Home },
    { href: "/explore", label: "Khám phá", icon: Compass },
  ];
  if (!user) return base;
  if (user.role === "student") return [...base, { href: "/my", label: "Khóa của tôi", icon: BookMarked }];
  // Chỉ giảng viên đã duyệt: GET /teacher/courses dùng require_teacher_approved (admin nhận 403).
  if (user.role === "teacher" && user.teacher_status === "approved")
    return [{ href: "/teach", label: "Khóa đang dạy", icon: GraduationCap }, ...base.slice(1)];
  return user.role === "teacher" ? base.slice(1) : base;
}

export function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
