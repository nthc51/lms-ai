"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenCheck, CalendarClock, HelpCircle, Layers, type LucideIcon, Zap } from "lucide-react";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type StudioKind = S["ArtifactKind"];
export type StudioItem = S["StudioItem"];
export type StudioOverview = S["StudioOverview"];
export type Artifact = S["ArtifactOut"];
export type Card = S["Card"];
export type LessonDocument = S["DocumentOut"];
export type ChunkDetail = S["ChunkOut"];
export type Note = S["NoteOut"];

export const KINDS: { kind: StudioKind; label: string; hint: string; icon: LucideIcon }[] = [
  { kind: "study_guide", label: "Đề cương ôn tập", hint: "Mục tiêu, khái niệm chính, câu hỏi tự kiểm tra", icon: BookOpenCheck },
  { kind: "briefing", label: "Tóm tắt nhanh", hint: "Đọc trong 2 phút", icon: Zap },
  { kind: "faq", label: "Hỏi đáp", hint: "Những chỗ học viên hay thắc mắc", icon: HelpCircle },
  { kind: "timeline", label: "Dòng thời gian", hint: "Mốc thời gian hoặc trình tự các bước", icon: CalendarClock },
  { kind: "flashcards", label: "Flashcard", hint: "Thẻ lật để ghi nhớ", icon: Layers },
];
export const kindLabel = (k: StudioKind) => KINDS.find((x) => x.kind === k)?.label ?? k;

export type Scope = { courseId: string; lessonId: string | null };

export const studioKeys = {
  overview: (s: Scope) => ["studio", s.courseId, s.lessonId] as const,
  artifact: (id: string) => ["studio-artifact", id] as const,
  documents: (lessonId: string) => ["lesson-documents", lessonId] as const,
  chunk: (id: string) => ["chunk", id] as const,
  followups: (messageId: string) => ["followups", messageId] as const,
  notes: (courseId: string | null, lessonId: string | null) => ["notes", courseId, lessonId] as const,
};

const POLL_MS = 3000;

/** Trạng thái 5 loại tài liệu học. Có loại đang sinh thì hỏi lại mỗi 3 giây cho tới khi xong. */
export function useStudioOverview(scope: Scope, enabled = true) {
  return useQuery({
    queryKey: studioKeys.overview(scope),
    enabled: enabled && !!scope.courseId,
    queryFn: () =>
      unwrap(api.GET("/api/v1/studio", { params: { query: { course_id: scope.courseId, lesson_id: scope.lessonId ?? undefined } } })),
    refetchInterval: (q) => (q.state.data?.items.some((i) => i.status === "generating") ? POLL_MS : false),
  });
}

export function useRequestArtifact(scope: Scope) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, force = false }: { kind: StudioKind; force?: boolean }) =>
      unwrap(
        api.POST("/api/v1/studio/{kind}", {
          params: { path: { kind } },
          body: { course_id: scope.courseId, lesson_id: scope.lessonId, force },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: studioKeys.overview(scope) }),
  });
}

export function useArtifact(id: string | null) {
  return useQuery({
    queryKey: studioKeys.artifact(id ?? "none"),
    enabled: !!id,
    queryFn: () => unwrap(api.GET("/api/v1/studio/artifacts/{artifact_id}", { params: { path: { artifact_id: id! } } })),
  });
}

export function useUpdateArtifact(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["ArtifactUpdate"]) =>
      unwrap(api.PATCH("/api/v1/studio/artifacts/{artifact_id}", { params: { path: { artifact_id: id } }, body })),
    onSuccess: (data) => {
      qc.setQueryData(studioKeys.artifact(id), data);
      return qc.invalidateQueries({ queryKey: ["studio"] });
    },
  });
}

/** Đánh dấu thẻ nhớ / chưa nhớ: cập nhật ngay trên màn hình, lỗi thì trả lại như cũ. */
export function useReviewCard(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ cardNo, known }: { cardNo: number; known: boolean }) =>
      unwrap(
        api.PUT("/api/v1/studio/artifacts/{artifact_id}/cards/{card_no}", {
          params: { path: { artifact_id: id, card_no: cardNo } },
          body: { known },
        }),
      ),
    onMutate: ({ cardNo, known }) => {
      const key = studioKeys.artifact(id);
      const previous = qc.getQueryData<Artifact>(key);
      qc.setQueryData<Artifact>(key, (old) =>
        old
          ? {
              ...old,
              known_cards: known
                ? [...new Set([...old.known_cards, cardNo])].sort((a, b) => a - b)
                : old.known_cards.filter((n) => n !== cardNo),
            }
          : old,
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(studioKeys.artifact(id), ctx.previous);
    },
  });
}

export function useLessonDocuments(lessonId: string, enabled = true) {
  return useQuery({
    queryKey: studioKeys.documents(lessonId),
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/documents", { params: { path: { lesson_id: lessonId } } })),
    // hướng dẫn tài liệu được sinh nền sau khi xử lý PDF: còn tài liệu chưa có hướng dẫn thì hỏi lại
    refetchInterval: (q) => (q.state.data?.some((d) => !d.guide || d.guide.status === "generating") ? POLL_MS * 2 : false),
  });
}

/** Mở PDF ở trang N trong thẻ mới (URL ký sẵn chỉ sống 1 giờ nên lấy lúc bấm). */
export async function openSourcePdf(sourceId: string, page?: number | null) {
  const win = window.open("", "_blank"); // mở trước khi await để trình duyệt không chặn popup
  try {
    const { url } = await unwrap(api.GET("/api/v1/sources/{source_id}/file", { params: { path: { source_id: sourceId } } }));
    const target = page ? `${url}#page=${page}` : url;
    if (win) win.location.href = target;
    else window.location.href = target;
  } catch (err) {
    win?.close();
    throw err;
  }
}

export function useChunk(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: studioKeys.chunk(id ?? "none"),
    enabled: enabled && !!id,
    staleTime: Infinity,
    queryFn: () => unwrap(api.GET("/api/v1/chunks/{chunk_id}", { params: { path: { chunk_id: id! } } })),
  });
}

/** 3 câu hỏi gợi ý sau một câu trả lời (POST nhưng lặp lại an toàn: sinh lần đầu rồi đọc lại). */
export function useFollowups(messageId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: studioKeys.followups(messageId ?? "none"),
    enabled: enabled && !!messageId,
    staleTime: Infinity,
    retry: false,
    queryFn: () =>
      unwrap(api.POST("/api/v1/tutor/messages/{message_id}/followups", { params: { path: { message_id: messageId! } } })),
  });
}

// ---------- ghi chú ----------

export function useNotes(courseId: string | null, lessonId: string | null = null, page = 1) {
  return useQuery({
    queryKey: [...studioKeys.notes(courseId, lessonId), page],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/notes", {
          params: { query: { course_id: courseId ?? undefined, lesson_id: lessonId ?? undefined, page, size: 50 } },
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((n) => n.status === "generating") ? POLL_MS : false),
  });
}

function useNotesMutation<A, R>(fn: (a: A) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ["notes"] }) });
}

export function useNoteMutations() {
  return {
    create: useNotesMutation((body: S["NoteIn"]) => unwrap(api.POST("/api/v1/notes", { body }))),
    fromMessage: useNotesMutation((messageId: string) =>
      unwrap(api.POST("/api/v1/notes/from-message", { body: { message_id: messageId } })),
    ),
    update: useNotesMutation(({ id, ...body }: { id: string } & S["NoteUpdate"]) =>
      unwrap(api.PATCH("/api/v1/notes/{note_id}", { params: { path: { note_id: id } }, body })),
    ),
    remove: useNotesMutation((id: string) => unwrap(api.DELETE("/api/v1/notes/{note_id}", { params: { path: { note_id: id } } }))),
    synthesize: useNotesMutation((body: S["NotesSynthesizeIn"]) => unwrap(api.POST("/api/v1/notes/synthesize", { body }))),
  };
}

/** Tải nội dung Markdown về máy. */
export function downloadMarkdown(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
