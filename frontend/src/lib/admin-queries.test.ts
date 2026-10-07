import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { actionLabel, useAdminActionsMutations, useAdminUsers } from "./admin-queries";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
  const invalidatedAdmin = () => spy.mock.calls.some(([f]) => JSON.stringify(f?.queryKey) === JSON.stringify(["admin"]));
  return { wrapper, invalidatedAdmin };
}

describe("admin-queries", () => {
  it("danh sách người dùng gửi đúng bộ lọc, bỏ q rỗng", async () => {
    let query = "";
    server.use(
      http.get(url("/admin/users"), ({ request }) => {
        query = new URL(request.url).search;
        return HttpResponse.json({ items: [], total: 0, page: 1, size: 20 });
      }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useAdminUsers({ role: "teacher", status: "pending", q: "", page: 2 }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const params = new URLSearchParams(query);
    expect(Object.fromEntries(params)).toEqual({ role: "teacher", status: "pending", page: "2", size: "20" });
  });

  it("thao tác xong thì làm mới cả khu quản trị; khóa không lý do gửi reason = null", async () => {
    let body: unknown;
    server.use(
      http.post(url("/admin/users/u1/lock"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "u1" });
      }),
    );
    const { wrapper, invalidatedAdmin } = setup();
    const { result } = renderHook(() => useAdminActionsMutations(), { wrapper });
    await result.current.lock.mutateAsync({ id: "u1", reason: "" });
    expect(body).toEqual({ reason: null });
    await waitFor(() => expect(invalidatedAdmin()).toBe(true));
  });

  it("nhãn thao tác tiếng Việt, mã lạ thì giữ nguyên", () => {
    expect(actionLabel("hide_course")).toBe("Ẩn khóa học");
    expect(actionLabel("something_new")).toBe("something_new");
  });
});
