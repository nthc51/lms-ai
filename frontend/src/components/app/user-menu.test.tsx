import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("next-themes", () => ({ useTheme: () => ({ theme: "light", resolvedTheme: "light", setTheme: vi.fn() }) }));
const logout = vi.fn(async () => {});
const auth = {
  status: "authenticated",
  logout,
  user: { id: "u1", email: "an@sv.vn", full_name: "Nguyễn Văn An", role: "student", teacher_status: null } as unknown,
};
vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => auth }));

import { initialOf, UserMenu } from "./user-menu";

afterEach(() => {
  push.mockClear();
  logout.mockClear();
  vi.unstubAllGlobals();
});

describe("UserMenu", () => {
  it("chữ đại diện là chữ đầu của tên gọi", () => {
    expect(initialOf("Nguyễn Văn An")).toBe("A");
    expect(initialOf("  trần thị  ánh ")).toBe("Á");
    expect(initialOf("")).toBe("?");
  });

  it("mở menu: có Hồ sơ cá nhân, Ghi chú và Đăng xuất; vào hồ sơ thì chuyển tới /account", async () => {
    render(<UserMenu compact />);
    // dạng gọn vẫn có tên cho trình đọc màn hình
    await userEvent.click(screen.getByRole("button", { name: /Nguyễn Văn An/ }));
    expect(screen.getByText("an@sv.vn · Học viên")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Ghi chú của tôi" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Hồ sơ cá nhân" }));
    expect(push).toHaveBeenCalledWith("/account");
  });

  it("đăng xuất rồi nạp lại trang chủ", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    render(<UserMenu />);
    await userEvent.click(screen.getByRole("button", { name: /Nguyễn Văn An/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Đăng xuất" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
    expect(logout).toHaveBeenCalledOnce();
  });

  it("quản trị viên không có mục Ghi chú; khách thấy nút Đăng nhập", async () => {
    auth.user = { id: "a1", email: "ad@x.vn", full_name: "Quản trị viên", role: "admin", teacher_status: null };
    const { unmount } = render(<UserMenu />);
    await userEvent.click(screen.getByRole("button", { name: /Quản trị viên/ }));
    expect(screen.queryByRole("menuitem", { name: "Ghi chú của tôi" })).not.toBeInTheDocument();
    unmount();
    auth.user = null;
    auth.status = "anonymous";
    render(<UserMenu />);
    expect(screen.getByRole("link", { name: "Đăng nhập" })).toHaveAttribute("href", "/login");
  });
});
