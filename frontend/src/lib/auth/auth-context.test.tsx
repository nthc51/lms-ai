import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import * as React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { setAccessToken } from "@/lib/api/token";
import { api as url, server } from "@/test/msw";
import { AuthProvider, useAuth } from "./auth-context";

const me = { id: "u1", email: "a@b.c", full_name: "A", role: "student", teacher_status: null };

let auth: ReturnType<typeof useAuth>;
let fetches = 0;

function Probe() {
  const current = useAuth();
  React.useEffect(() => {
    auth = current;
  });
  // truy vấn phụ thuộc người dùng, khóa không có user id (đúng kiểu useCourse trước khi gate)
  const q = useQuery({
    queryKey: ["probe"],
    queryFn: async () => {
      fetches += 1;
      const r = await fetch(url("/probe"), { headers: { Authorization: "Bearer x" } });
      return (await r.json()) as { who: string };
    },
  });
  return <div>{`${current.status}|${current.userId}|${q.data?.who ?? "-"}`}</div>;
}

function setup(qc = new QueryClient()) {
  render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return qc;
}

afterEach(() => {
  fetches = 0;
  setAccessToken(null);
});

describe("AuthProvider: cache theo người dùng", () => {
  it("khôi phục phiên xong thì reset cache tạo lúc ẩn danh và tải lại theo người dùng", async () => {
    let authed = false;
    server.use(
      http.post(url("/auth/refresh"), () => HttpResponse.json({ access_token: "t1" })),
      http.get(url("/me"), () => {
        authed = true;
        return HttpResponse.json(me);
      }),
      http.get(url("/probe"), () => HttpResponse.json({ who: authed ? "u1" : "guest" })),
    );
    setup();
    // lần tải đầu (khi còn "loading") thấy dữ liệu khách; sau khi có phiên phải thành dữ liệu của u1
    await waitFor(() => expect(screen.getByText("authenticated|u1|u1")).toBeInTheDocument());
    expect(fetches).toBeGreaterThanOrEqual(2);
  });

  it("ẩn danh → ẩn danh không reset cache", async () => {
    server.use(
      http.post(url("/auth/refresh"), () => new HttpResponse(null, { status: 401 })),
      http.get(url("/probe"), () => HttpResponse.json({ who: "guest" })),
    );
    setup();
    await waitFor(() => expect(screen.getByText("anonymous|null|guest")).toBeInTheDocument());
    expect(fetches).toBe(1);
  });

  it("đăng nhập rồi đăng xuất đều dọn cache của người dùng trước", async () => {
    let who = "guest";
    server.use(
      http.post(url("/auth/refresh"), () => new HttpResponse(null, { status: 401 })),
      http.post(url("/auth/login"), () => HttpResponse.json({ access_token: "t2" })),
      http.post(url("/auth/logout"), () => new HttpResponse(null, { status: 204 })),
      http.get(url("/me"), () => {
        who = "u1";
        return HttpResponse.json(me);
      }),
      http.get(url("/probe"), () => HttpResponse.json({ who })),
    );
    setup();
    await waitFor(() => expect(screen.getByText("anonymous|null|guest")).toBeInTheDocument());

    await act(async () => {
      await auth.login("a@b.c", "pw");
    });
    await waitFor(() => expect(screen.getByText("authenticated|u1|u1")).toBeInTheDocument());

    who = "guest";
    await act(async () => {
      await auth.logout();
    });
    await waitFor(() => expect(screen.getByText("anonymous|null|guest")).toBeInTheDocument());
  });
});
