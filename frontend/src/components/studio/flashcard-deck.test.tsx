import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { Artifact } from "@/lib/studio/queries";
import { api as url, server } from "@/test/msw";
import { FlashcardDeck } from "./flashcard-deck";

const artifact = {
  id: "a1",
  course_id: "c1",
  lesson_id: null,
  kind: "flashcards",
  status: "ready",
  content_md: "",
  cards: [
    { front: "Câu 1", back: "Đáp 1", sources: [] },
    { front: "Câu 2", back: "Đáp 2", sources: [] },
    { front: "Câu 3", back: "Đáp 3", sources: [] },
  ],
  citations: [],
  error_msg: null,
  stale: false,
  reviewed: false,
  created_at: "2026-10-01T00:00:00Z",
  known_cards: [0],
} as Artifact;

function setup(canEdit = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <FlashcardDeck artifact={artifact} canEdit={canEdit} lessonId={null} />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("FlashcardDeck", () => {
  it("Space lật thẻ, N đánh dấu nhớ và sang thẻ sau", async () => {
    const marked: string[] = [];
    server.use(
      http.put(url("/studio/artifacts/a1/cards/:n"), async ({ params, request }) => {
        marked.push(`${params.n}:${JSON.stringify(await request.json())}`);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = setup();
    expect(screen.getByText("Câu 1")).toBeInTheDocument();
    await user.keyboard(" ");
    expect(screen.getByText("Đáp 1")).toBeInTheDocument();
    await user.keyboard("n");
    await waitFor(() => expect(marked).toEqual(['0:{"known":true}']));
    expect(screen.getByText("Câu 2")).toBeInTheDocument();
    expect(screen.getByText("Thẻ 2/3")).toBeInTheDocument();
  });

  // Lệch plan (5d): tổ hợp phím (Ctrl+C sao chép) không được đánh dấu thẻ
  it("Ctrl+C không đánh dấu thẻ, phím C thường vẫn đánh dấu chưa nhớ", async () => {
    const marked: string[] = [];
    server.use(
      http.put(url("/studio/artifacts/a1/cards/:n"), async ({ params, request }) => {
        marked.push(`${params.n}:${JSON.stringify(await request.json())}`);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = setup();
    await user.keyboard("{Control>}c{/Control}");
    await user.keyboard("{Meta>}n{/Meta}");
    expect(screen.getByText("Câu 1")).toBeInTheDocument();
    expect(screen.getByText("Thẻ 1/3")).toBeInTheDocument();
    expect(marked).toEqual([]);
    await user.keyboard("c");
    await waitFor(() => expect(marked).toEqual(['0:{"known":false}']));
    expect(screen.getByText("Câu 2")).toBeInTheDocument();
  });

  it("chỉ ôn thẻ chưa nhớ: bỏ các thẻ đã nhớ khỏi bộ", async () => {
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Chỉ ôn thẻ chưa nhớ" }));
    expect(screen.getByText("Thẻ 1/2")).toBeInTheDocument();
    expect(screen.getByText("Câu 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xem tất cả thẻ" })).toHaveAttribute("aria-pressed", "true");
  });

  // Lệch plan: tên của nút thẻ là nội dung thẻ (không bị aria-label che), gợi ý là mô tả
  it("trình đọc màn hình đọc được mặt trước rồi mặt sau của thẻ", async () => {
    const user = setup();
    const card = screen.getByRole("button", { name: /Câu 1/ });
    expect(card).toHaveAccessibleDescription(/bấm để lật xem đáp án/);
    await user.keyboard(" ");
    expect(screen.getByRole("button", { name: /Đáp 1/ })).toBeInTheDocument();
  });

  it("focus ở nút khác trong bộ thẻ thì phím tắt không chạy", async () => {
    const user = setup();
    screen.getByRole("button", { name: "Chỉ ôn thẻ chưa nhớ" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByText("Thẻ 1/3")).toBeInTheDocument();
    screen.getByRole("button", { name: /Câu 1/ }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByText("Thẻ 2/3")).toBeInTheDocument();
  });

  // Lệch plan: xóa thẻ phải xác nhận (quy ước §0.5)
  it("Xóa thẻ hỏi xác nhận: Hủy giữ thẻ, xác nhận thì xóa", async () => {
    const sent: unknown[] = [];
    server.use(
      http.patch(url("/studio/artifacts/a1"), async ({ request }) => {
        const body = (await request.json()) as { cards: { front: string }[] };
        sent.push(body);
        return HttpResponse.json({ ...artifact, cards: body.cards, reviewed: true });
      }),
    );
    const user = setup(true);
    await user.click(screen.getByRole("button", { name: /Sửa thẻ này/ }));
    await user.click(screen.getByRole("button", { name: "Xóa thẻ" }));
    let dialog = screen.getByRole("alertdialog", { name: "Xóa thẻ này?" });
    expect(within(dialog).getByRole("button", { name: "Hủy" })).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(sent).toEqual([]);
    expect(screen.getByLabelText("Mặt trước (câu hỏi)")).toHaveValue("Câu 1");

    await user.click(screen.getByRole("button", { name: "Xóa thẻ" }));
    dialog = screen.getByRole("alertdialog", { name: "Xóa thẻ này?" });
    await user.click(within(dialog).getByRole("button", { name: "Xóa thẻ" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect((sent[0] as { cards: { front: string }[] }).cards.map((c) => c.front)).toEqual(["Câu 2", "Câu 3"]);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });
});
