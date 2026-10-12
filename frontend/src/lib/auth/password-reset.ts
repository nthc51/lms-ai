"use client";

import { useMutation } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

/** Xin link đặt lại mật khẩu. API luôn trả 202 (không lộ email nào đã đăng ký); 429 khi xin quá nhiều lần. */
export function useForgotPassword() {
  return useMutation({
    mutationFn: (email: string) => unwrap(api.POST("/api/v1/auth/forgot-password", { body: { email } })),
  });
}

/** Đặt mật khẩu mới bằng token trong link. Thành công thì mọi phiên đăng nhập cũ bị thu hồi. */
export function useResetPassword() {
  return useMutation({
    mutationFn: (body: { token: string; password: string }) =>
      unwrap(api.POST("/api/v1/auth/reset-password", { body })),
  });
}

export function forgotErrorMessage(err: unknown) {
  if (err instanceof ApiError && err.status === 429) {
    const minutes = Math.max(1, Math.ceil((err.retryAfter ?? 60) / 60));
    return `Bạn đã yêu cầu quá nhiều lần. Thử lại sau khoảng ${minutes} phút.`;
  }
  return err instanceof Error ? err.message : "Không gửi được email";
}

/** Link hỏng / hết hạn / đã dùng: người dùng cần xin link mới (khác lỗi mạng, lỗi mật khẩu). */
export function isDeadResetLink(err: unknown) {
  return err instanceof ApiError && (err.code === "INVALID_TOKEN" || err.code === "TOKEN_EXPIRED");
}
