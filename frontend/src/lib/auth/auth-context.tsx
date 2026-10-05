"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { api, apiBase, refreshAccessToken, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { setAccessToken } from "@/lib/api/token";

export type User = components["schemas"]["UserOut"];
type Status = "loading" | "authenticated" | "anonymous";

type AuthValue = {
  user: User | null;
  /** id người dùng hiện tại (null khi chưa đăng nhập hoặc đang khôi phục phiên). */
  userId: string | null;
  status: Status;
  login: (email: string, password: string) => Promise<User>;
  register: (data: components["schemas"]["RegisterIn"]) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = React.createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = React.useState<User | null>(null);
  const [status, setStatus] = React.useState<Status>("loading");

  const loadMe = React.useCallback(async () => {
    const me = await unwrap(api.GET("/api/v1/me"));
    setUser(me);
    setStatus("authenticated");
    return me;
  }, []);

  // Mở trang: thử khôi phục phiên từ cookie refresh.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await refreshAccessToken();
      if (cancelled) return;
      if (!token) {
        setStatus("anonymous");
        return;
      }
      try {
        await loadMe();
      } catch {
        if (!cancelled) setStatus("anonymous");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadMe]);

  // Dữ liệu phụ thuộc người dùng (vd. is_enrolled/is_owner của khóa học) không được sống sót qua lần
  // đổi người dùng: khi phiên khôi phục xong, đăng nhập, đăng xuất hay refresh ra người khác thì
  // reset toàn bộ cache (query đang hiển thị sẽ tự tải lại). Lúc đang "loading" token chưa có nên
  // coi như ẩn danh: ẩn danh → ẩn danh không cần reset.
  const userId = user?.id ?? null;
  const lastUserId = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (status === "loading" || lastUserId.current === userId) return;
    lastUserId.current = userId;
    void qc.resetQueries();
  }, [status, userId, qc]);

  const login = React.useCallback(
    async (email: string, password: string) => {
      const { access_token } = await unwrap(api.POST("/api/v1/auth/login", { body: { email, password } }));
      setAccessToken(access_token);
      return loadMe();
    },
    [loadMe],
  );

  const register = React.useCallback(async (data: components["schemas"]["RegisterIn"]) => {
    await unwrap(api.POST("/api/v1/auth/register", { body: data }));
  }, []);

  const logout = React.useCallback(async () => {
    try {
      await fetch(`${apiBase()}/api/v1/auth/logout`, { method: "POST", credentials: "include" });
    } finally {
      setAccessToken(null);
      setUser(null);
      setStatus("anonymous");
      qc.clear();
    }
  }, [qc]);

  const value = React.useMemo(
    () => ({ user, userId, status, login, register, logout }),
    [user, userId, status, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth phải nằm trong <AuthProvider>");
  return ctx;
}

/** Giảng viên đã duyệt hoặc admin: được tạo/sửa khóa học (khớp require_staff ở backend). */
export function isStaff(user: User | null) {
  return !!user && (user.role === "admin" || (user.role === "teacher" && user.teacher_status === "approved"));
}
