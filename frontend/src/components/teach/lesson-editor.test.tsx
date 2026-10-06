import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { LessonEditor } from "./lesson-editor";

vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({ status: "authenticated", user: { role: "teacher", teacher_status: "approved" } }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));

const lessonOf = (id: string) => ({ id, title: `Bài ${id}`, content_md: `Nội dung ${id}`, position: 0, duration_sec: null });
const course = {
  id: "c1",
  slug: "toan",
  title: "Toán 12",
  description: "",
  status: "draft",
  sections: [{ id: "s1", title: "Chương 1", position: 0, lessons: [lessonOf("l1"), lessonOf("l2")] }],
};

function setup(lessonId = "l1") {
  const patches: { id: string; body: Record<string, unknown> }[] = [];
  server.use(
    http.get(url("/courses/toan"), () => HttpResponse.json(course)),
    http.get(url("/lessons/:id"), ({ params }) => HttpResponse.json(lessonOf(params.id as string))),
    http.get(url("/lessons/:id/video"), () => new HttpResponse(null, { status: 404 })),
    http.get(url("/lessons/:id/sources"), () => HttpResponse.json([])),
    http.patch(url("/lessons/:id"), async ({ params, request }) => {
      patches.push({ id: params.id as string, body: (await request.json()) as Record<string, unknown> });
      return HttpResponse.json(lessonOf(params.id as string));
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (id: string) => (
    <QueryClientProvider client={qc}>
      <LessonEditor slug="toan" lessonId={id} />
    </QueryClientProvider>
  );
  const view = render(ui(lessonId));
  return { patches, view, ui, user: userEvent.setup({ delay: null }) };
}

const settle = () => new Promise((r) => setTimeout(r, 50));

describe("tự lưu khi rời trình soạn bài", () => {
  it("lưu phần đang chờ khi unmount", async () => {
    const { patches, view, user } = setup();
    await user.type(await screen.findByLabelText("Nội dung bài (markdown)"), " thêm");
    view.unmount();
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toMatchObject({ id: "l1", body: { content_md: "Nội dung l1 thêm" } });
  });

  it("không lưu khi tên bài trống", async () => {
    const { patches, view, user } = setup();
    await user.clear(await screen.findByLabelText("Tên bài"));
    view.unmount();
    await settle();
    expect(patches).toHaveLength(0);
  });

  it("đổi bài: bản sửa của bài A chỉ lưu vào A, không ghi vào B", async () => {
    const { patches, view, ui, user } = setup("l1");
    await user.type(await screen.findByLabelText("Nội dung bài (markdown)"), " thêm");
    view.rerender(ui("l2"));
    await waitFor(() => expect(screen.getByLabelText("Tên bài")).toHaveValue("Bài l2"));
    await settle();
    expect(patches).toHaveLength(1);
    expect(patches[0].id).toBe("l1");
    expect(screen.getByLabelText("Nội dung bài (markdown)")).toHaveValue("Nội dung l2");
  });
});
