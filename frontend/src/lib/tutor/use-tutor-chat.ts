"use client";

import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { api, apiBase, authFetch, unwrap } from "@/lib/api/client";
import { ApiError, errorMessage, toApiError } from "@/lib/api/errors";
import { readSse } from "@/lib/api/sse";
import type { ChatMessage, Citation, Source } from "./types";

type Scope = { courseId: string; lessonId: string | null };

const AI_ERROR = "AI Tutor tạm thời không trả lời được. Câu hỏi của bạn đã được lưu, bấm Thử lại sau ít phút.";

function fromServer(m: {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  refused: boolean;
  truncated: boolean;
  feedback: number | null;
}): ChatMessage {
  return { ...m, sources: [], status: m.truncated ? "stopped" : "done" };
}

/**
 * Gửi câu hỏi từ ngoài ô nhập (tab Tài liệu) được không: không khi đang trả lời, đang tải lịch sử
 * (gửi lúc chưa biết phiên sẽ tạo phiên thứ hai) hoặc đang đếm ngược sau 429.
 */
export function canAskTutor(chat: { busy: boolean; loadingHistory: boolean; retryAt: number | null }) {
  return !chat.busy && !chat.loadingHistory && !chat.retryAt;
}

/**
 * Hội thoại AI Tutor của một bài (hoặc cả khóa khi lessonId = null).
 * - Dùng lại phiên gần nhất cùng phạm vi; chưa có thì tạo khi gửi câu đầu.
 * - Trả lời stream qua SSE: sources → token… → done | error (error có thể là event đầu).
 * - Nội dung cuối lấy từ done.content (token stream có thể còn [n] thô / phần bị lọc).
 */
export function useTutorChat({ courseId, lessonId }: Scope, enabled = true) {
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [retryAt, setRetryAt] = React.useState<number | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  // Lệch plan: đổi bài/khóa thì xóa hội thoại cũ ngay trong render (không để lộ chat của bài trước),
  // còn abort stream đang chạy làm ở cleanup của effect bên dưới (cả khi unmount).
  const scopeKey = `${courseId}:${lessonId ?? ""}`;
  const [prevScope, setPrevScope] = React.useState(scopeKey);
  if (prevScope !== scopeKey) {
    setPrevScope(scopeKey);
    setSessionId(null);
    setMessages([]);
    setBusy(false);
    setRetryAt(null);
  }
  React.useEffect(
    () => () => {
      abortRef.current?.abort();
      abortRef.current = null; // stream cũ thấy mình không còn "hiện hành" nên thôi vá state
    },
    [scopeKey],
  );

  const availability = useQuery({
    queryKey: ["tutor-availability", courseId, lessonId],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/tutor/availability", {
          params: { query: { course_id: courseId, lesson_id: lessonId ?? undefined } },
        }),
      ),
    enabled,
  });

  const history = useQuery({
    queryKey: ["tutor-history", courseId, lessonId],
    enabled,
    staleTime: Infinity, // sau lần tải đầu, state cục bộ là nguồn chính
    gcTime: 0,
    queryFn: async () => {
      const sessions = await unwrap(
        api.GET("/api/v1/tutor/sessions", { params: { query: { course_id: courseId, size: 100 } } }),
      );
      const session = sessions.items.find((s) => (s.lesson_id ?? null) === lessonId);
      if (!session) return { sessionId: null, messages: [] as ChatMessage[] };
      const page = await unwrap(
        api.GET("/api/v1/tutor/sessions/{session_id}/messages", {
          params: { path: { session_id: session.id }, query: { size: 100 } },
        }),
      );
      return { sessionId: session.id, messages: page.items.map(fromServer) };
    },
  });

  React.useEffect(() => {
    if (history.data) {
      setSessionId(history.data.sessionId);
      setMessages(history.data.messages);
    }
  }, [history.data]);

  const patchLastMessage = (fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((ms) => (ms.length ? [...ms.slice(0, -1), fn(ms[ms.length - 1])] : ms));

  const ensureSession = async (isCurrent: () => boolean) => {
    if (sessionId) return sessionId;
    const s = await unwrap(
      api.POST("/api/v1/tutor/sessions", { body: { course_id: courseId, lesson_id: lessonId } }),
    );
    if (isCurrent()) setSessionId(s.id);
    return s.id;
  };

  const send = React.useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text || busy) return;
      setBusy(true);
      const now = Date.now();
      setMessages((ms) => [
        ...ms,
        { id: `local-u-${now}`, role: "user", content: text, citations: [], sources: [], refused: false, truncated: false, feedback: null, status: "done" },
        { id: `local-a-${now}`, role: "assistant", content: "", citations: [], sources: [], refused: false, truncated: false, feedback: null, status: "streaming" },
      ]);
      const controller = new AbortController();
      abortRef.current = controller;
      // Lệch plan: chỉ vá state khi stream này còn là stream hiện hành (đổi bài thì abortRef bị xóa).
      const isCurrent = () => abortRef.current === controller;
      const patchLast = (fn: (m: ChatMessage) => ChatMessage) => {
        if (isCurrent()) patchLastMessage(fn);
      };
      try {
        const sid = await ensureSession(isCurrent);
        const res = await authFetch(
          new Request(`${apiBase()}/api/v1/tutor/sessions/${sid}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify({ content: text }),
            signal: controller.signal,
          }),
        );
        if (!res.ok || !res.body) throw await toApiError(res);
        let gotDone = false;
        for await (const ev of readSse(res.body, controller.signal)) {
          if (controller.signal.aborted) break; // Lệch plan: đã bấm Dừng thì bỏ các event còn trong bộ đệm
          const data = JSON.parse(ev.data);
          if (ev.event === "sources") patchLast((m) => ({ ...m, sources: data.sources as Source[] }));
          else if (ev.event === "token") patchLast((m) => ({ ...m, content: m.content + data.text }));
          else if (ev.event === "done") {
            gotDone = true;
            patchLast((m) => ({
              ...m,
              id: data.message_id,
              content: data.content,
              citations: data.citations,
              refused: data.refused,
              status: "done",
            }));
          } else if (ev.event === "error") {
            gotDone = true;
            patchLast((m) => ({ ...m, status: "error", truncated: true, error: data.message || AI_ERROR }));
          }
        }
        if (!gotDone && !controller.signal.aborted)
          patchLast((m) => ({ ...m, status: "error", truncated: true, error: "Mất kết nối giữa chừng. " + AI_ERROR }));
        // Lệch plan: readSse có thể return (không throw) khi đã abort → đánh dấu đã dừng.
        else if (!gotDone) patchLast((m) => ({ ...m, status: "stopped", truncated: true }));
      } catch (err) {
        if (controller.signal.aborted) {
          patchLast((m) => ({ ...m, status: "stopped", truncated: true }));
        } else {
          if (err instanceof ApiError && err.status === 429 && err.retryAfter) setRetryAt(Date.now() + err.retryAfter * 1000);
          // lỗi trước khi stream mở (429, 403...): bỏ bong bóng trả lời rỗng, báo lỗi ở đó
          patchLast((m) => ({ ...m, status: "error", error: errorMessage(err) }));
        }
      } finally {
        // Lệch plan: luôn abort để nhả body/kết nối khi thoát sớm (catch đã phân loại lỗi trước đó).
        controller.abort();
        if (isCurrent()) {
          abortRef.current = null;
          setBusy(false);
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [busy, sessionId, courseId, lessonId],
  );

  const clearRetry = React.useCallback(() => setRetryAt(null), []);
  const stop = React.useCallback(() => abortRef.current?.abort(), []);

  /** Gửi lại câu hỏi gần nhất (câu cũ đã được lưu phía server nên lịch sử sẽ có 2 lần hỏi). */
  const retry = React.useCallback(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages((ms) => ms.slice(0, -2));
    void send(lastUser.content);
  }, [messages, send]);

  const feedback = React.useCallback(async (messageId: string, value: 1 | -1 | null) => {
    setMessages((ms) => ms.map((m) => (m.id === messageId ? { ...m, feedback: value } : m)));
    await unwrap(
      api.POST("/api/v1/tutor/messages/{message_id}/feedback", { params: { path: { message_id: messageId } }, body: { value } }),
    );
  }, []);

  return {
    availability: availability.data,
    // Lệch plan: isPending (không phải isLoading) để khóa ô nhập tới khi biết phiên hiện có.
    loadingHistory: enabled && history.isPending,
    historyError: history.error,
    messages,
    busy,
    retryAt,
    clearRetry,
    send,
    stop,
    retry,
    feedback,
  };
}
