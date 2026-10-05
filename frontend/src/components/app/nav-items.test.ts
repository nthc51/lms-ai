import { describe, expect, it } from "vitest";
import type { User } from "@/lib/auth/auth-context";
import { isActive, navItems } from "./nav-items";

const user = (role: User["role"], teacher_status: User["teacher_status"] = null) =>
  ({ id: "1", email: "a@b.c", full_name: "A", role, teacher_status }) as User;

describe("navItems", () => {
  it("khách: Trang chủ, Khám phá", () => {
    expect(navItems(null).map((i) => i.label)).toEqual(["Trang chủ", "Khám phá"]);
  });
  it("học viên có Khóa của tôi", () => {
    expect(navItems(user("student")).map((i) => i.label)).toEqual(["Trang chủ", "Khám phá", "Khóa của tôi"]);
  });
  it("giảng viên đã duyệt có Khóa đang dạy; chờ duyệt thì không", () => {
    expect(navItems(user("teacher", "approved")).map((i) => i.href)).toEqual(["/teach", "/explore"]);
    expect(navItems(user("teacher", "pending")).map((i) => i.href)).toEqual(["/explore"]);
  });
  it("tối đa 3 mục (thanh dưới thêm mục Tài khoản = 4)", () => {
    for (const r of ["student", "teacher", "admin"] as const) expect(navItems(user(r, "approved")).length).toBeLessThanOrEqual(3);
  });
  it("isActive khớp tiền tố nhưng / chỉ khớp chính nó", () => {
    expect(isActive("/teach/abc", "/teach")).toBe(true);
    expect(isActive("/explore", "/")).toBe(false);
  });
  it("quản trị viên không có Khóa đang dạy (API /teacher/courses chỉ cho giảng viên)", () => {
    expect(navItems(user("admin")).map((i) => i.href)).toEqual(["/", "/explore"]);
    expect(navItems(user("admin", "approved")).map((i) => i.href)).toEqual(["/", "/explore"]);
  });
});
