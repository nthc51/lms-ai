import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";

vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ status: "authenticated" }) }));

import { NotificationBell } from "./notification-bell";

const item = (id: string, read: boolean) => ({
  id,
  kind: "comment_reply",
  title: `Thông báo ${id}`,
  body: "Nội dung ngắn",
  link: `/learn/c/l#thao-luan`,
  read,
  created_at: new Date().toISOString(),
});

function setup({ unread = 2, stream }: { unread?: number; stream?: string } = {}) {
  const marked: string[] = [];
  server.use(
    http.get(url("/me/notifications/unread"), () => HttpResponse.json({ unread })),
    http.get(url("/me/notifications"), () =>
      HttpResponse.json({ items: [item("n1", false), item("n2", true)], total: 2, page: 1, size: 10, unread }),
    ),
    // luồng SSE: mặc định treo (không gửi gì) như máy chủ đang giữ kết nối
    http.get(url("/me/notifications/stream"), () =>
      stream === undefined
        ? new HttpResponse(new ReadableStream(), { headers: { "Content-Type": "text/event-stream" } })
        : new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream" } }),
    ),
    http.post(url("/me/notifications/:id/read"), ({ params }) => {
      marked.push(params.id as string);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <NotificationBell />
    </QueryClientProvider>,
  );
  return { marked, unmount: view.unmount };
}

describe("NotificationBell", () => {
  it("nút chuông đọc được số chưa đọc; mở ra thấy danh sách, bấm thông báo chưa đọc thì đánh dấu đã đọc", async () => {
    const user = userEvent.setup();
    const { marked, unmount } = setup();
    const bell = await screen.findByRole("button", { name: "Thông báo, 2 chưa đọc" });
    await user.click(bell);
    expect(await screen.findByText("Thông báo n1")).toBeInTheDocument();
    expect(screen.getByText("Chưa đọc:")).toBeInTheDocument(); // chỉ n1 có nhãn cho trình đọc màn hình
    await user.click(screen.getByRole("link", { name: /Thông báo n1/ }));
    await waitFor(() => expect(marked).toEqual(["n1"]));
    unmount();
  });

  it("luồng SSE cập nhật số chưa đọc mà không cần tải lại trang", async () => {
    const { unmount } = setup({ unread: 0, stream: 'event: unread\ndata: {"unread": 5, "latest": null}\n\n' });
    expect(await screen.findByRole("button", { name: "Thông báo, 5 chưa đọc" })).toBeInTheDocument();
    unmount(); // hủy vòng lặp kết nối lại
  });

  it("không có gì chưa đọc: không có huy hiệu, nút 'Đã đọc hết' bị khóa", async () => {
    const user = userEvent.setup();
    const { unmount } = setup({ unread: 0 });
    await user.click(await screen.findByRole("button", { name: "Thông báo" }));
    expect(await screen.findByRole("button", { name: /Đã đọc hết/ })).toBeDisabled();
    unmount();
  });
});
