import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { useCourse } from "./queries";

const auth = vi.hoisted(() => ({ status: "loading" as "loading" | "anonymous" | "authenticated" }));
vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ status: auth.status }) }));

function Probe() {
  useCourse("toan-12");
  return null;
}

function setup() {
  let calls = 0;
  server.use(
    http.get(url("/courses/toan-12"), () => {
      calls += 1;
      return HttpResponse.json({ id: "c1", slug: "toan-12", sections: [] });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (
    <QueryClientProvider client={qc}>
      <Probe />
    </QueryClientProvider>
  );
  return { ui, qc, calls: () => calls };
}

describe("useCourse", () => {
  beforeEach(() => {
    auth.status = "loading";
  });

  it("không tải khóa học khi phiên đang được khôi phục", async () => {
    const { ui, calls } = setup();
    render(ui);
    await new Promise((r) => setTimeout(r, 50));
    expect(calls()).toBe(0);
  });

  it.each(["anonymous", "authenticated"] as const)("tải khóa học khi trạng thái là %s", async (status) => {
    auth.status = status;
    const { ui, calls } = setup();
    render(ui);
    await waitFor(() => expect(calls()).toBe(1));
  });

  it("tải ngay khi phiên khôi phục xong", async () => {
    const { ui, qc, calls } = setup();
    const { rerender } = render(ui);
    await new Promise((r) => setTimeout(r, 30));
    expect(calls()).toBe(0);
    auth.status = "anonymous";
    rerender(<QueryClientProvider client={qc}><Probe /></QueryClientProvider>);
    await waitFor(() => expect(calls()).toBe(1));
  });
});
