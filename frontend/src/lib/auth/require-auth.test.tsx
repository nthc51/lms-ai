import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/my" }));
const auth = { status: "anonymous", user: null as unknown };
vi.mock("./auth-context", () => ({
  useAuth: () => auth,
  isStaff: (u: { role: string; teacher_status: string } | null) => u?.teacher_status === "approved",
}));

import { RequireAuth } from "./require-auth";

describe("RequireAuth", () => {
  it("chưa đăng nhập thì chuyển tới /login kèm next", () => {
    render(<RequireAuth>nội dung</RequireAuth>);
    expect(replace).toHaveBeenCalledWith("/login?next=%2Fmy");
    expect(screen.queryByText("nội dung")).not.toBeInTheDocument();
  });

  it("giảng viên chờ duyệt thấy thông báo thay vì trang soạn khóa", () => {
    auth.status = "authenticated";
    auth.user = { role: "teacher", teacher_status: "pending" };
    render(<RequireAuth staff>soạn khóa</RequireAuth>);
    expect(screen.getByText(/đang chờ quản trị viên duyệt/)).toBeInTheDocument();
  });
});
