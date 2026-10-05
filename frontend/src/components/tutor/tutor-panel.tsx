"use client";

import { MessageCircleQuestion, RotateCcw, SendHorizontal, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Markdown } from "@/components/content/markdown";
import { Button } from "@/components/ui/button";
import { Skeleton, Tip } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { linkCitations } from "@/lib/tutor/citations";
import type { ChatMessage } from "@/lib/tutor/types";
import type { useTutorChat } from "@/lib/tutor/use-tutor-chat";
import { cn } from "@/lib/utils";
import { CitationChip } from "./citation-chip";

type Chat = ReturnType<typeof useTutorChat>;

/** Nội dung panel AI Tutor (dùng chung cho cột phải desktop và khung trượt điện thoại). */
export function TutorPanel({
  chat,
  lessonId,
  onSeek,
  onOpenLesson,
}: {
  chat: Chat;
  lessonId: string | null;
  onSeek?: (sec: number) => void;
  onOpenLesson?: (lessonId: string) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const listRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const countdown = useCountdown(chat.retryAt, chat.clearRetry);
  const unavailable = chat.availability && !chat.availability.available;

  React.useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // tự cuộn xuống khi có chữ mới, trừ khi người dùng đang cuộn lên đọc lại
  const last = chat.messages[chat.messages.length - 1];
  React.useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [last?.content, chat.messages.length]);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!draft.trim() || chat.busy || chat.loadingHistory || countdown > 0) return;
    void chat.send(draft);
    setDraft("");
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={listRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite" aria-busy={chat.busy}>
        {chat.loadingHistory ? (
          <div className="space-y-3" aria-label="Đang tải hội thoại">
            <Skeleton className="ml-auto h-10 w-2/3" />
            <Skeleton className="h-20 w-5/6" />
          </div>
        ) : chat.messages.length === 0 ? (
          <div className="flex flex-col items-center gap-2 pt-10 text-center text-muted-foreground">
            <MessageCircleQuestion className="size-8" aria-hidden />
            <p>Hỏi bất cứ điều gì về bài này. AI chỉ trả lời dựa trên tài liệu của khóa và ghi rõ nguồn.</p>
          </div>
        ) : (
          chat.messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="ml-auto max-w-[85%] rounded-lg bg-muted px-3 py-2 whitespace-pre-wrap">
                {m.content}
              </div>
            ) : (
              <AssistantMessage
                key={m.id}
                m={m}
                lessonId={lessonId}
                onSeek={onSeek}
                onOpenLesson={onOpenLesson}
                onRetry={chat.retry}
                onFeedback={async (v) => {
                  try {
                    await chat.feedback(m.id, v);
                    if (v !== null) toast("Cảm ơn góp ý của bạn");
                  } catch (err) {
                    toast.error(errorMessage(err));
                  }
                }}
              />
            ),
          )
        )}
      </div>

      <form onSubmit={submit} className="border-t p-3">
        {unavailable ? (
          <p className="mb-2 text-sm text-muted-foreground">{chat.availability?.message ?? "AI Tutor chưa sẵn sàng cho bài này."}</p>
        ) : null}
        <div className="flex items-end gap-2">
          <label htmlFor="tutor-input" className="sr-only">
            Câu hỏi cho AI Tutor
          </label>
          <textarea
            id="tutor-input"
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) submit(e);
            }}
            rows={2}
            maxLength={2000}
            disabled={!!unavailable || chat.loadingHistory}
            placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
            className="max-h-40 min-h-11 flex-1 resize-none rounded-md border bg-surface px-3 py-2 text-base md:text-sm"
          />
          {chat.busy ? (
            <Button type="button" variant="outline" onClick={chat.stop}>
              <Square /> Dừng
            </Button>
          ) : (
            <Button type="submit" disabled={!draft.trim() || countdown > 0 || !!unavailable || chat.loadingHistory}>
              <SendHorizontal /> {countdown > 0 ? `${countdown}s` : "Gửi"}
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

function AssistantMessage({
  m,
  lessonId,
  onSeek,
  onOpenLesson,
  onRetry,
  onFeedback,
}: {
  m: ChatMessage;
  lessonId: string | null;
  onSeek?: (sec: number) => void;
  onOpenLesson?: (id: string) => void;
  onRetry: () => void;
  onFeedback: (v: 1 | -1 | null) => void;
}) {
  const numbers = new Set([...m.sources.map((s) => s.n), ...m.citations.map((c) => c.n)]);
  const body = linkCitations(m.content, numbers);
  return (
    <div className="max-w-[95%]">
      {m.sources.length > 0 && m.status === "streaming" ? (
        <p className="mb-1 text-xs text-muted-foreground">Đã tìm thấy {m.sources.length} đoạn tài liệu liên quan…</p>
      ) : null}
      {m.content ? (
        <Markdown
          className={cn("text-[15px] [--reader-size:15px]", m.refused && "text-muted-foreground")}
          components={{
            a: ({ href, children }) => {
              const match = href?.match(/^#cite-(\d+)$/);
              if (!match) return <a href={href}>{children}</a>;
              const n = Number(match[1]);
              return (
                <CitationChip
                  n={n}
                  source={m.sources.find((s) => s.n === n)}
                  citation={m.citations.find((c) => c.n === n)}
                  currentLessonId={lessonId}
                  onSeek={onSeek}
                  onOpenLesson={onOpenLesson}
                />
              );
            },
          }}
        >
          {body}
        </Markdown>
      ) : m.status === "streaming" ? (
        <div className="space-y-2" aria-label="AI đang soạn câu trả lời">
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ) : null}

      {m.status === "error" ? (
        <div role="alert" className="mt-2 rounded-md border border-destructive/40 p-3 text-sm">
          <p>{m.error}</p>
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            <RotateCcw /> Thử lại
          </Button>
        </div>
      ) : null}
      {m.status === "stopped" ? <p className="mt-1 text-xs text-muted-foreground">Đã dừng.</p> : null}

      {m.status === "done" && !m.id.startsWith("local-") ? (
        <div className="mt-1 flex gap-1">
          <Tip label="Câu trả lời hữu ích">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Hữu ích"
              aria-pressed={m.feedback === 1}
              className={cn("size-8", m.feedback === 1 && "text-success")}
              onClick={() => onFeedback(m.feedback === 1 ? null : 1)}
            >
              <ThumbsUp />
            </Button>
          </Tip>
          <Tip label="Câu trả lời chưa tốt">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Chưa tốt"
              aria-pressed={m.feedback === -1}
              className={cn("size-8", m.feedback === -1 && "text-destructive")}
              onClick={() => onFeedback(m.feedback === -1 ? null : -1)}
            >
              <ThumbsDown />
            </Button>
          </Tip>
        </div>
      ) : null}
    </div>
  );
}

/** Số giây còn lại tới retryAt (429), về 0 thì gọi onDone. */
function useCountdown(until: number | null, onDone: () => void) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!until) return;
    const id = window.setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= until) onDone();
    }, 1000);
    return () => window.clearInterval(id);
  }, [until, onDone]);
  return until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0;
}
