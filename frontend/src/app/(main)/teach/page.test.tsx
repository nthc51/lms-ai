import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import TeachPage from "./page";

const auth = vi.hoisted(() => ({ user: { role: "admin" } as { role: string; teacher_status?: string } }));
vi.mock("@/lib/auth/auth-context", async (orig) => ({
  ...(await orig<typeof import("@/lib/auth/auth-context")>()),
  useAuth: () => ({ status: "authenticated", user: auth.user }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/teach",
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TeachPage />
    </QueryClientProvider>,
  );
}

describe("/teach", () => {
  it("admin thấy thông báo, không gọi API danh sách khóa của giảng viên", async () => {
    const list = vi.fn(() => HttpResponse.json({ items: [], total: 0, page: 1, size: 50 }));
    server.use(http.get(url("/teacher/courses"), list));
    auth.user = { role: "admin" };
    renderPage();
    expect(await screen.findByText(/Trang này dành cho giảng viên/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /danh sách khóa học/ })).toHaveAttribute("href", "/admin/courses");
    await new Promise((r) => setTimeout(r, 50));
    expect(list).not.toHaveBeenCalled();
  });

  it("giảng viên đã duyệt vẫn thấy danh sách khóa", async () => {
    server.use(
      http.get(url("/teacher/courses"), () =>
        HttpResponse.json({ items: [{ id: "c1", slug: "toan", title: "Toán 12", status: "draft" }], total: 1, page: 1, size: 50 }),
      ),
    );
    auth.user = { role: "teacher", teacher_status: "approved" };
    renderPage();
    expect(await screen.findByText("Toán 12")).toBeInTheDocument();
    expect(screen.queryByText(/Trang này dành cho giảng viên/)).not.toBeInTheDocument();
  });
});
