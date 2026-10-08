import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <FlashcardDeck artifact={artifact} canEdit={false} lessonId={null} />
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
});
