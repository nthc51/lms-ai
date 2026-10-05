import createClient, { type Middleware } from "openapi-fetch";
import { ApiError, networkError, toApiError } from "./errors";
import type { paths } from "./schema";
import { getAccessToken, setAccessToken } from "./token";

/** Gốc URL của API. Mặc định cùng origin với trang (Next rewrites /api/v1 → FastAPI). */
export function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE;
  return typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
}

let refreshing: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  const res = await fetch(`${apiBase()}/api/v1/auth/refresh`, { method: "POST", credentials: "include" });
  if (!res.ok) {
    // Chỉ 401/403 nghĩa là phiên đã hết; 5xx thì giữ nguyên token, lần sau thử lại.
    if (res.status === 401 || res.status === 403) setAccessToken(null);
    return null;
  }
  const { access_token } = (await res.json()) as { access_token: string };
  setAccessToken(access_token);
  return access_token;
}

/**
 * Gọi /auth/refresh đúng 1 lần dù nhiều request cùng gặp 401 (single-flight trong tab).
 * Giữa các tab thì xếp hàng bằng Web Locks: backend thu hồi mọi refresh token nếu một token
 * đã xoay vòng bị dùng lại (TOKEN_REUSED), nên tab sau phải đợi tab trước nhận cookie mới.
 */
export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= (async () => {
    try {
      const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
      return locks ? await locks.request("auth-refresh", doRefresh) : await doRefresh();
    } catch {
      return null; // lỗi mạng: giữ nguyên trạng thái, không đăng xuất
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

const NO_REFRESH = ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"];

/**
 * fetch có gắn Bearer token; gặp 401 thì refresh một lần rồi gửi lại.
 * Dùng chung cho openapi-fetch, SSE và mọi lệnh gọi tay.
 */
export async function authFetch(input: Request): Promise<Response> {
  const send = (token: string | null) => {
    const req = input.clone();
    if (token) req.headers.set("Authorization", `Bearer ${token}`);
    return fetch(req, { credentials: "include" } as RequestInit);
  };
  let res: Response;
  try {
    res = await send(getAccessToken());
  } catch {
    throw networkError();
  }
  const path = new URL(input.url).pathname;
  if (res.status === 401 && !NO_REFRESH.includes(path)) {
    const token = await refreshAccessToken();
    if (token) {
      try {
        res = await send(token);
      } catch {
        throw networkError();
      }
    }
  }
  return res;
}

const throwOnError: Middleware = {
  async onResponse({ response }) {
    if (!response.ok) throw await toApiError(response);
    return response;
  },
};

// Module này chỉ được gọi từ client component, nên apiBase() chạy trong trình duyệt.
export const api = createClient<paths>({ baseUrl: apiBase(), fetch: (req) => authFetch(req) });
api.use(throwOnError);

/** Lấy `data` hoặc ném ApiError; dùng trong queryFn/mutationFn của TanStack Query. */
export async function unwrap<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined) throw error instanceof ApiError ? error : await toApiError(response);
  return data as T;
}
