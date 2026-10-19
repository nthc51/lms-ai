"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { api, apiBase, authFetch, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { readSse } from "@/lib/api/sse";

export type Notification = components["schemas"]["NotificationOut"];

export const notifKeys = {
  all: ["notifications"] as const,
  list: ["notifications", "list"] as const,
  unread: ["notifications", "unread"] as const,
};

/** 10 thông báo mới nhất (mở khi bấm chuông). */
export function useNotifications(enabled: boolean) {
  return useQuery({
    queryKey: notifKeys.list,
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/me/notifications", { params: { query: { size: 10 } } })),
  });
}

/** Số chưa đọc. Luồng SSE cập nhật thẳng vào cache này, nên không cần tải lại định kỳ. */
export function useUnreadCount(enabled: boolean) {
  return useQuery({
    queryKey: notifKeys.unread,
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/me/notifications/unread")),
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/v1/me/notifications/{notification_id}/read", { params: { path: { notification_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifKeys.all }),
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/me/notifications/read-all")),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifKeys.all }),
  });
}

const RETRY_MIN_MS = 2_000;
const RETRY_MAX_MS = 30_000;

/**
 * Mở luồng SSE /me/notifications/stream và ghi số chưa đọc vào cache (B6). Mất kết nối thì mở lại sau 2 giây,
 * mỗi lần lỗi liên tiếp gấp đôi thời gian chờ (tối đa 30 giây). authFetch tự refresh access token khi gặp 401.
 */
export function useNotificationStream(enabled: boolean) {
  const qc = useQueryClient();
  React.useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    let delay = RETRY_MIN_MS;
    (async () => {
      while (!ctrl.signal.aborted) {
        try {
          const res = await authFetch(new Request(`${apiBase()}/api/v1/me/notifications/stream`, { signal: ctrl.signal }));
          if (res.ok && res.body) {
            for await (const ev of readSse(res.body, ctrl.signal)) {
              if (ev.event !== "unread") continue;
              delay = RETRY_MIN_MS; // đã nhận dữ liệu: kết nối tốt
              const data = JSON.parse(ev.data) as { unread: number };
              const prev = qc.getQueryData<{ unread: number }>(notifKeys.unread);
              // lệnh GET /unread gửi trước có thể về sau và ghi đè số mới hơn: hủy nó đi
              await qc.cancelQueries({ queryKey: notifKeys.unread });
              qc.setQueryData(notifKeys.unread, { unread: data.unread });
              if (prev && prev.unread !== data.unread) void qc.invalidateQueries({ queryKey: notifKeys.list });
            }
          }
        } catch {
          // mất mạng, tab bị đóng (abort) hay máy chủ khởi động lại: thử lại bên dưới
        }
        if (ctrl.signal.aborted) return;
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, RETRY_MAX_MS);
      }
    })();
    return () => ctrl.abort();
  }, [enabled, qc]);
}
