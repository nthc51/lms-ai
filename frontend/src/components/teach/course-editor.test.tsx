import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { CourseEditor } from "./course-editor";

vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({ status: "authenticated", user: { role: "teacher", teacher_status: "approved" } }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));

const lesson = { id: "l1", title: "Bài 1", position: 0 };
function course(lessons: unknown[]) {
  return {
    id: "c1",
    slug: "toan",
    title: "Toán 12",
    description: "",
    status: "draft",
    sections: [{ id: "s1", title: "Chương 1", position: 0, lessons }],
  };
}

function setup(lessons: unknown[]) {
  const patches: unknown[] = [];
  server.use(
    http.get(url("/courses/toan"), () => HttpResponse.json(course(lessons))),
    http.patch(url("/courses/c1"), async ({ request }) => {
      patches.push(await request.json());
      return HttpResponse.json(course(lessons));
    }),
    http.delete(url("/courses/c1"), () => new HttpResponse(null, { status: 204 })),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <CourseEditor slug="toan" />
    </QueryClientProvider>,
  );
  return { patches, view, user: userEvent.setup({ delay: null }) };
}

const settle = () => new Promise((r) => setTimeout(r, 50));

describe("nút Xuất bản", () => {
  it("bị vô hiệu kèm gợi ý khi khóa chưa có bài", async () => {
    setup([]);
    const btn = await screen.findByRole("button", { name: /Xuất bản/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAccessibleDescription("Thêm ít nhất 1 bài để xuất bản");
  });

  it("bấm được khi có ít nhất 1 bài", async () => {
    setup([lesson]);
    const btn = await screen.findByRole("button", { name: /Xuất bản/ });
    expect(btn).toBeEnabled();
    expect(screen.queryByText("Thêm ít nhất 1 bài để xuất bản")).not.toBeInTheDocument();
  });
});

describe("tự lưu khi đóng trình soạn", () => {
  it("lưu phần đang chờ khi unmount", async () => {
    const { patches, view, user } = setup([lesson]);
    await user.type(await screen.findByLabelText("Tên khóa học"), " mới");
    view.unmount();
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toMatchObject({ title: "Toán 12 mới" });
  });

  it("không lưu khi tên dưới 3 ký tự", async () => {
    const { patches, view, user } = setup([lesson]);
    const title = await screen.findByLabelText("Tên khóa học");
    await user.clear(title);
    await user.type(title, "ab");
    view.unmount();
    await settle();
    expect(patches).toHaveLength(0);
  });

  it("không lưu sau khi khóa đã bị xóa", async () => {
    const { patches, view, user } = setup([lesson]);
    await screen.findByLabelText("Tên khóa học");
    await user.click(screen.getByRole("button", { name: /Xóa khóa học/ }));
    await user.type(await screen.findByLabelText(/để xác nhận/), "Toán 12");
    await user.click(screen.getByRole("button", { name: "Xóa vĩnh viễn" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    await user.type(screen.getByLabelText("Tên khóa học"), " x");
    view.unmount();
    await settle();
    expect(patches).toHaveLength(0);
  });
});
