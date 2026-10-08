"use client";

import { FileText, Loader2, MessageCircleQuestion } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { openSourcePdf, useLessonDocuments } from "@/lib/studio/queries";

/**
 * Tài liệu của bài + hướng dẫn (tóm tắt, chủ đề, câu hỏi gợi ý). Bấm câu gợi ý là hỏi AI Tutor luôn.
 * disabled: AI Tutor chưa nhận câu hỏi được (đang trả lời, đang tải lịch sử, đang chờ hết giới hạn 429).
 */
export function DocumentsPanel({ lessonId, onAsk, disabled = false }: { lessonId: string; onAsk: (question: string) => void; disabled?: boolean }) {
  const docs = useLessonDocuments(lessonId);
  if (docs.isPending)
    return (
      <div className="space-y-3 p-4" aria-busy="true" aria-label="Đang tải">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  if (docs.isError)
    return (
      <p role="alert" className="p-4 text-sm text-destructive">
        {errorMessage(docs.error)}
      </p>
    );
  if (docs.data.length === 0)
    return <p className="m-4 rounded-md border border-dashed p-4 text-sm text-muted-foreground">Bài này chưa có tài liệu PDF nào.</p>;
  return (
    <ul className="h-full space-y-4 overflow-y-auto p-4">
      {docs.data.map((d) => (
        <li key={d.source_id} className="rounded-lg border bg-surface p-4">
          <div className="flex items-start gap-2">
            <FileText className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold">{d.title}</h3>
              <p className="text-xs text-muted-foreground">{d.status === "ready" ? `${d.page_count} trang` : d.file_name}</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => openSourcePdf(d.source_id).catch((err) => toast.error(errorMessage(err)))}>
              Mở PDF
            </Button>
          </div>
          {d.status === "pending" || d.status === "processing" ? (
            <p role="status" className="mt-3 flex items-center gap-1.5 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden /> AI đang đọc tài liệu. Bạn vẫn mở PDF được ngay.
            </p>
          ) : d.status === "failed" ? (
            <p className="mt-3 text-sm text-destructive">AI không đọc được tài liệu này. Tải lại file ở trang soạn bài.</p>
          ) : !d.guide || d.guide.status === "generating" ? (
            <p role="status" className="mt-3 flex items-center gap-1.5 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden /> AI đang đọc tài liệu để viết hướng dẫn…
            </p>
          ) : d.guide.status === "failed" ? (
            <p className="mt-3 text-sm text-muted-foreground">Chưa có hướng dẫn cho tài liệu này.</p>
          ) : (
            <div className="mt-3 space-y-3 text-sm">
              <p>{d.guide.summary}</p>
              {d.guide.topics.length ? (
                <div>
                  <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Chủ đề chính</h4>
                  <div className="flex flex-wrap gap-1.5">
                    {d.guide.topics.map((t) => (
                      <Badge key={t}>{t}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              {d.guide.questions.length ? (
                <div>
                  <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Hỏi AI về tài liệu này</h4>
                  <ul className="space-y-1.5">
                    {d.guide.questions.map((q) => (
                      <li key={q}>
                        <button
                          type="button"
                          onClick={() => onAsk(q)}
                          disabled={disabled}
                          className="flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                          {q}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
