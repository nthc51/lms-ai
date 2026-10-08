import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it } from "vitest";
import { api as url, server } from "@/test/msw";
import { type Artifact, documentsPollInterval, GUIDE_WAIT_MS, type LessonDocument, studioKeys, useReviewCard, useStudioOverview } from "./queries";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, wrapper };
}

const artifact = (known: number[]): Artifact =>
  ({
    id: "a1",
    course_id: "c1",
    lesson_id: null,
    kind: "flashcards",
    status: "ready",
    content_md: "",
    cards: [
      { front: "A", back: "a", sources: [] },
      { front: "B", back: "b", sources: [] },
    ],
    citations: [],
    error_msg: null,
    stale: false,
    reviewed: false,
    created_at: "2026-10-01T00:00:00Z",
    known_cards: known,
  }) as Artifact;

describe("studio queries", () => {
  it("tổng quan Studio: phạm vi cả khóa không gửi lesson_id", async () => {
    let search = "";
    server.use(
      http.get(url("/studio"), ({ request }) => {
        search = new URL(request.url).search;
        return HttpResponse.json({ has_content: true, can_regenerate: false, items: [] });
      }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useStudioOverview({ courseId: "c1", lessonId: null }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(Object.fromEntries(new URLSearchParams(search))).toEqual({ course_id: "c1" });
  });

  it("đánh dấu thẻ: cập nhật ngay trên màn hình, lỗi thì trả lại như cũ", async () => {
    server.use(http.put(url("/studio/artifacts/a1/cards/1"), () => HttpResponse.json({ error: { code: "X", message: "x", details: {}, request_id: null } }, { status: 500 })));
    const { qc, wrapper } = setup();
    qc.setQueryData(studioKeys.artifact("a1"), artifact([0]));
    const { result } = renderHook(() => useReviewCard("a1"), { wrapper });
    act(() => result.current.mutate({ cardNo: 1, known: true }));
    await waitFor(() => expect(qc.getQueryData<Artifact>(studioKeys.artifact("a1"))?.known_cards).toEqual([0, 1]));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData<Artifact>(studioKeys.artifact("a1"))?.known_cards).toEqual([0]);
  });
});

describe("documentsPollInterval", () => {
  const doc = (over: Record<string, unknown>) => ({ source_id: "s1", status: "ready", guide: null, ...over }) as unknown as LessonDocument;
  const T = 1_000_000;

  it("còn processing/pending thì hỏi lại mãi", () => {
    expect(documentsPollInterval([doc({ status: "processing" })], T + 10 * GUIDE_WAIT_MS, new Map())).toBeGreaterThan(0);
    expect(documentsPollInterval([doc({ status: "pending" })], T + 10 * GUIDE_WAIT_MS, new Map())).toBeGreaterThan(0);
  });

  it("hướng dẫn đang sinh thì hỏi lại", () => {
    expect(documentsPollInterval([doc({ guide: { status: "generating" } })], T, new Map())).toBeGreaterThan(0);
  });

  it("ready chưa có hướng dẫn: hỏi trong cửa sổ rồi dừng", () => {
    const seen = new Map<string, number>();
    expect(documentsPollInterval([doc({})], T, seen)).toBeGreaterThan(0);
    expect(documentsPollInterval([doc({})], T + GUIDE_WAIT_MS - 1, seen)).toBeGreaterThan(0);
    expect(documentsPollInterval([doc({})], T + GUIDE_WAIT_MS, seen)).toBe(false);
  });

  it("xử lý lâu rồi mới ready: cửa sổ tính từ lúc ready", () => {
    const seen = new Map<string, number>();
    for (let i = 0; i < 100; i++) expect(documentsPollInterval([doc({ status: "processing" })], T + i * 6000, seen)).toBeGreaterThan(0);
    const ready = T + 100 * 6000; // > 2 phút sau lần đầu
    expect(documentsPollInterval([doc({})], ready, seen)).toBeGreaterThan(0);
    expect(documentsPollInterval([doc({})], ready + GUIDE_WAIT_MS - 1, seen)).toBeGreaterThan(0);
    expect(documentsPollInterval([doc({})], ready + GUIDE_WAIT_MS, seen)).toBe(false);
  });

  it("có hướng dẫn thì bỏ mốc; không có gì chờ thì dừng", () => {
    const seen = new Map<string, number>([["s1", T]]);
    expect(documentsPollInterval([doc({ guide: { status: "ready" } }), doc({ source_id: "s2", status: "failed" })], T + 1, seen)).toBe(false);
    expect(seen.size).toBe(0);
    expect(documentsPollInterval(undefined, T, seen)).toBe(false);
  });
});
