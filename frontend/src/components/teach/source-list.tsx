"use client";

import { AlertTriangle, CheckCircle2, FileText, Loader2, RefreshCw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge, Skeleton } from "@/components/ui/misc";
import { Markdown } from "@/components/content/markdown";
import { ErrorState } from "@/components/app/states";
import { errorMessage } from "@/lib/api/errors";
import { type SourceOut, useLessonSources, useSourceActions, useSourcePages } from "@/lib/teach-queries";
import { FileDrop } from "./file-drop";

const STATUS = {
  pending: { label: "Đang chờ xử lý", tone: "neutral" },
  processing: { label: "Đang xử lý", tone: "primary" },
  ready: { label: "Sẵn sàng", tone: "success" },
  failed: { label: "Lỗi", tone: "destructive" },
} as const;

/**
 * Tài liệu PDF của bài: tải lên → server trích văn bản + tạo embedding (job nền).
 * Danh sách tự hỏi lại trạng thái mỗi 3 giây khi còn tài liệu đang xử lý.
 */
export function SourceList({ lessonId }: { lessonId: string }) {
  const sources = useLessonSources(lessonId);
  const actions = useSourceActions(lessonId);
  const [viewing, setViewing] = React.useState<SourceOut | null>(null);

  return (
    <section aria-labelledby="sources-title" className="space-y-3">
      <h2 id="sources-title" className="font-semibold">
        Tài liệu cho AI Tutor
      </h2>
      <p className="text-sm text-muted-foreground">AI Tutor chỉ trả lời dựa trên các tài liệu ở trạng thái Sẵn sàng.</p>

      {sources.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : sources.isError ? (
        <ErrorState error={sources.error} onRetry={() => sources.refetch()} />
      ) : sources.data.length ? (
        <ul className="space-y-2">
          {sources.data.map((s, i) => (
            <li key={s.id} className="rounded-md border p-3 text-sm">
              <div className="flex items-center gap-2">
                <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="flex-1">Tài liệu {i + 1}</span>
                <Badge tone={STATUS[s.status].tone}>
                  {s.status === "processing" || s.status === "pending" ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
                  {s.status === "ready" ? <CheckCircle2 className="size-3" aria-hidden /> : null}
                  {s.status === "failed" ? <AlertTriangle className="size-3" aria-hidden /> : null}
                  {STATUS[s.status].label}
                </Badge>
              </div>
              {s.status === "ready" ? (
                <p className="mt-1 text-muted-foreground">
                  {s.page_count} trang · {s.chunk_count} đoạn{s.vision_pages ? ` · ${s.vision_pages} trang đọc bằng AI vision` : ""}
                </p>
              ) : null}
              {s.warning ? <p className="mt-1 text-accent">{s.warning}</p> : null}
              {s.status === "failed" && s.error_msg ? <p className="mt-1 text-destructive">{s.error_msg}</p> : null}
              <div className="mt-2 flex gap-2">
                {s.status === "ready" ? (
                  <Button variant="link" size="sm" onClick={() => setViewing(s)}>
                    Xem các trang đã trích
                  </Button>
                ) : null}
                {s.status === "failed" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    loading={actions.reprocess.isPending && actions.reprocess.variables === s.id}
                    loadingText="Đang gửi…"
                    onClick={() =>
                      actions.reprocess.mutate(s.id, {
                        onSuccess: () => toast("Đã gửi xử lý lại"),
                        onError: (err) => toast.error(errorMessage(err)),
                      })
                    }
                  >
                    <RefreshCw /> Xử lý lại
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Chưa có tài liệu nào.</p>
      )}

      <FileDrop
        kind="pdf"
        label="Chọn file PDF"
        onUploaded={async (assetId) => {
          await actions.attach.mutateAsync(assetId);
          toast.success("Đã tải lên. Hệ thống đang xử lý tài liệu…");
        }}
      />

      <SourcePagesDialog source={viewing} onClose={() => setViewing(null)} />
    </section>
  );
}

function SourcePagesDialog({ source, onClose }: { source: SourceOut | null; onClose: () => void }) {
  const [page, setPage] = React.useState(1);
  const pages = useSourcePages(source?.id ?? null, page);
  const totalPages = pages.data ? Math.ceil(pages.data.total / pages.data.size) : 1;
  return (
    <Dialog
      open={!!source}
      onOpenChange={(o) => {
        if (!o) {
          onClose();
          setPage(1);
        }
      }}
    >
      <DialogContent title="Các trang đã trích" className="max-h-[85dvh] max-w-2xl overflow-y-auto">
        {pages.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : pages.isError ? (
          <ErrorState error={pages.error} onRetry={() => pages.refetch()} />
        ) : (
          <div className="space-y-6">
            {pages.data.items.map((p) => (
              <article key={p.page_no} className="rounded-md border p-3">
                <div className="mb-2 flex items-center gap-2 text-sm">
                  <span className="font-medium">Trang {p.page_no}</span>
                  <Badge tone={p.extraction_method === "vision" ? "accent" : "neutral"}>
                    {p.extraction_method === "vision" ? "Vision" : "Text"}
                  </Badge>
                </div>
                <Markdown className="text-sm [--reader-size:14px]">{p.markdown}</Markdown>
              </article>
            ))}
            <div className="flex items-center justify-between">
              <Button variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Trang trước
              </Button>
              <span className="text-sm text-muted-foreground">
                {page}/{totalPages}
              </span>
              <Button variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                Trang sau
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
