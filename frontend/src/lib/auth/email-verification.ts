"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

/** Gửi lại email xác nhận. API luôn trả 202 (không lộ email nào đã đăng ký); 429 khi gửi quá 3 lần/giờ. */
export function useResendVerification() {
  return useMutation({
    mutationFn: (email: string) => unwrap(api.POST("/api/v1/auth/resend-verification", { body: { email } })),
  });
}

/** Xác nhận email bằng token trong link. Chỉ gửi một lần cho mỗi token (không thử lại, không tải lại). */
export function useVerifyEmail(token: string | null) {
  return useQuery({
    queryKey: ["verify-email", token],
    queryFn: () => unwrap(api.POST("/api/v1/auth/verify-email", { body: { token: token! } })),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function resendErrorMessage(err: unknown) {
  if (err instanceof ApiError && err.status === 429) {
    const minutes = Math.max(1, Math.ceil((err.retryAfter ?? 60) / 60));
    return `Bạn đã yêu cầu gửi lại quá nhiều lần. Thử lại sau khoảng ${minutes} phút.`;
  }
  return err instanceof Error ? err.message : "Không gửi lại được email";
}
