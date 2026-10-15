import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getAccessToken, setAccessToken } from "@/lib/api/token";
import { api as url, server } from "@/test/msw";

const reloadUser = vi.fn(async () => ({}));
vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ reloadUser }) }));
const toast = vi.hoisted(() => ({ success: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import { PasswordForm, ProfileForm } from "./profile-forms";

const user = { id: "u1", email: "an@sv.vn", full_name: "Nguyễn Văn An", role: "student", teacher_status: null, email_verified: true } as const;
const apiErr = (status: number, code: string, message: string, headers: Record<string, string> = {}) =>
  HttpResponse.json({ error: { code, message, details: {} } }, { status, headers });

function wrap(ui: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  reloadUser.mockClear();
  toast.success.mockClear();
  setAccessToken(null);
});

describe("ProfileForm", () => {
  it("chỉ bật nút Lưu khi đã sửa; gửi họ tên đã gọn khoảng trắng rồi tải lại người dùng", async () => {
    let body: unknown = null;
    server.use(
      http.patch(url("/me"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...user, full_name: "Nguyễn Văn Bình" });
      }),
    );
    wrap(<ProfileForm user={user} />);
    const save = screen.getByRole("button", { name: "Lưu họ tên" });
    expect(save).toBeDisabled();
    const input = screen.getByLabelText("Họ tên");
    await userEvent.clear(input);
    await userEvent.type(input, "  Nguyễn   Văn Bình ");
    await userEvent.click(save);
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith("Đã lưu họ tên"));
    expect(body).toEqual({ full_name: "Nguyễn Văn Bình" });
    expect(reloadUser).toHaveBeenCalledOnce();
    expect(input).toHaveValue("Nguyễn Văn Bình");
  });

  it("họ tên toàn khoảng trắng: báo lỗi, không gọi API", async () => {
    wrap(<ProfileForm user={user} />);
    const input = screen.getByLabelText("Họ tên");
    await userEvent.clear(input);
    await userEvent.type(input, "   ");
    await userEvent.click(screen.getByRole("button", { name: "Lưu họ tên" }));
    expect(await screen.findByText("Nhập họ tên")).toBeInTheDocument();
  });
});

describe("PasswordForm", () => {
  async function fill(current: string, next: string, confirm = next) {
    await userEvent.type(screen.getByLabelText("Mật khẩu hiện tại"), current);
    await userEvent.type(screen.getByLabelText("Mật khẩu mới"), next);
    await userEvent.type(screen.getByLabelText("Nhập lại mật khẩu mới"), confirm);
    await userEvent.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
  }

  it("thành công: dùng ngay access token mới và xóa trắng các ô", async () => {
    let body: unknown = null;
    server.use(
      http.post(url("/me/password"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ access_token: "tok-moi", token_type: "bearer" });
      }),
    );
    wrap(<PasswordForm />);
    await fill("password123", "mat-khau-moi-1");
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(body).toEqual({ current_password: "password123", new_password: "mat-khau-moi-1" });
    expect(getAccessToken()).toBe("tok-moi");
    expect(screen.getByLabelText("Mật khẩu hiện tại")).toHaveValue("");
  });

  it("hai ô mật khẩu mới không khớp thì không gửi", async () => {
    wrap(<PasswordForm />);
    await fill("password123", "mat-khau-moi-1", "khac-hoan-toan");
    expect(await screen.findByText("Hai mật khẩu chưa khớp")).toBeInTheDocument();
  });

  it("sai mật khẩu hiện tại thì báo ở đúng ô đó; thử quá nhiều lần thì báo thời gian chờ", async () => {
    let calls = 0;
    server.use(
      http.post(url("/me/password"), () => {
        calls += 1;
        return calls === 1
          ? apiErr(400, "WRONG_PASSWORD", "Mật khẩu hiện tại không đúng")
          : apiErr(429, "RATE_LIMITED", "Chậm lại", { "Retry-After": "1800" });
      }),
    );
    wrap(<PasswordForm />);
    await fill("sai-roi", "mat-khau-moi-1");
    const current = screen.getByLabelText("Mật khẩu hiện tại");
    expect(await screen.findByText("Mật khẩu hiện tại không đúng")).toBeInTheDocument();
    expect(current).toHaveAttribute("aria-invalid", "true");
    await userEvent.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Thử lại sau khoảng 30 phút");
  });
});
