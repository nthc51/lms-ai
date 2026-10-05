import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { api as url, server } from "@/test/msw";
import { api, unwrap } from "./client";
import { ApiError } from "./errors";
import { getAccessToken, setAccessToken } from "./token";

describe("api client", () => {
  beforeEach(() => setAccessToken(null));

  it("gắn Bearer token vào request", async () => {
    setAccessToken("t1");
    server.use(
      http.get(url("/me"), ({ request }) =>
        HttpResponse.json({ id: "u1", auth: request.headers.get("Authorization") }),
      ),
    );
    const me = (await unwrap(api.GET("/api/v1/me"))) as unknown as { auth: string };
    expect(me.auth).toBe("Bearer t1");
  });

  it("gặp 401 thì refresh đúng 1 lần cho nhiều request song song rồi gửi lại", async () => {
    setAccessToken("old");
    let refreshCalls = 0;
    server.use(
      http.get(url("/me"), ({ request }) =>
        request.headers.get("Authorization") === "Bearer new"
          ? HttpResponse.json({ id: "u1" })
          : HttpResponse.json({ error: { code: "INVALID_TOKEN", message: "x" } }, { status: 401 }),
      ),
      http.post(url("/auth/refresh"), () => {
        refreshCalls += 1;
        return HttpResponse.json({ access_token: "new", token_type: "bearer" });
      }),
    );
    await Promise.all([unwrap(api.GET("/api/v1/me")), unwrap(api.GET("/api/v1/me"))]);
    expect(refreshCalls).toBe(1);
    expect(getAccessToken()).toBe("new");
  });

  it("refresh thất bại thì xóa token và ném ApiError 401", async () => {
    setAccessToken("old");
    server.use(
      http.get(url("/me"), () =>
        HttpResponse.json({ error: { code: "INVALID_TOKEN", message: "Phiên hết hạn" } }, { status: 401 }),
      ),
      http.post(url("/auth/refresh"), () =>
        HttpResponse.json({ error: { code: "INVALID_TOKEN", message: "x" } }, { status: 401 }),
      ),
    );
    await expect(unwrap(api.GET("/api/v1/me"))).rejects.toMatchObject({ status: 401 });
    expect(getAccessToken()).toBeNull();
  });

  it("đọc code, message, request_id và Retry-After từ thân lỗi", async () => {
    server.use(
      http.get(url("/me"), () =>
        HttpResponse.json(
          { error: { code: "RATE_LIMITED", message: "Chậm lại", details: {}, request_id: "rq-1" } },
          { status: 429, headers: { "Retry-After": "40" } },
        ),
      ),
    );
    const err = (await unwrap(api.GET("/api/v1/me")).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "RATE_LIMITED", requestId: "rq-1", retryAfter: 40 });
  });
});
