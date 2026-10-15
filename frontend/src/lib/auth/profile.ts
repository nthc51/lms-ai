"use client";

import { useMutation } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { setAccessToken } from "@/lib/api/token";

/** Sửa họ tên. Trả UserOut mới. */
export function useUpdateProfile() {
  return useMutation({
    mutationFn: (full_name: string) => unwrap(api.PATCH("/api/v1/me", { body: { full_name } })),
  });
}

/**
 * Đổi mật khẩu khi đang đăng nhập. Backend thu hồi mọi phiên cũ và cấp phiên mới cho trình duyệt này
 * (cookie refresh mới + access token trả về), nên dùng ngay token mới để không bị văng ra.
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: async (body: { current_password: string; new_password: string }) => {
      const { access_token } = await unwrap(api.POST("/api/v1/me/password", { body }));
      setAccessToken(access_token);
    },
  });
}

/** Lỗi đổi mật khẩu thuộc ô nào: "current" (sai mật khẩu hiện tại), "new" (trùng mật khẩu cũ) hay chung. */
export function passwordErrorField(err: unknown): "current" | "new" | null {
  if (!(err instanceof ApiError)) return null;
  if (err.code === "WRONG_PASSWORD") return "current";
  if (err.code === "SAME_PASSWORD") return "new";
  return null;
}

export function passwordErrorMessage(err: unknown) {
  if (err instanceof ApiError && err.status === 429) {
    const minutes = Math.max(1, Math.ceil((err.retryAfter ?? 60) / 60));
    return `Bạn đã thử quá nhiều lần. Thử lại sau khoảng ${minutes} phút.`;
  }
  return err instanceof Error ? err.message : "Không đổi được mật khẩu";
}
