"use client";

import { Download, ExternalLink, Eye, EyeOff, FileText, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { downloadSourcePdf, type LessonDocument, openSourcePdf, sourceFileUrl, useLessonDocuments } from "@/lib/studio/queries";

/** Màn hình rộng thì xem PDF ngay trong trang; điện thoại (trình duyệt di động hiện PDF trong khung rất kém) mở thẻ mới. */
function canViewInline() {
  return typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches;
}

/**
 * Tài liệu PDF của bài, hiện ngay dưới nội dung bài, kể cả khi bài chưa có nội dung chữ và kể cả khi AI còn đang
 * đọc tài liệu: học viên xem / tải được file ngay. AI Tutor và Studio dùng tài liệu khi đã "sẵn sàng".
 */
export function LessonMaterials({ lessonId }: { lessonId: string }) {
  const docs = useLessonDocuments(lessonId);
  const [viewing, setViewing] = React.useState<{ id: string; url: string } | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  if (!docs.data?.length) return null;

  async function view(doc: LessonDocument) {
    if (viewing?.id === doc.source_id) return setViewing(null);
    if (!canViewInline()) return openSourcePdf(doc.source_id).catch((err) => toast.error(errorMessage(err)));
    setBusy(doc.source_id);
    try {
      setViewing({ id: doc.source_id, url: await sourceFileUrl(doc.source_id) });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="materials-title" className="mt-8">
      <h2 id="materials-title" className="text-lg font-semibold">
        Tài liệu của bài
      </h2>
      <ul className="mt-3 space-y-3">
        {docs.data.map((d) => {
          const open = viewing?.id === d.source_id;
          return (
            <li key={d.source_id} className="rounded-lg border bg-surface p-4">
              <div className="flex flex-wrap items-center gap-3">
                <FileText className="size-5 shrink-0 text-primary" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="font-medium break-words">{d.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {d.status === "ready" ? (
                      `${d.page_count} trang`
                    ) : d.status === "failed" ? (
                      <span className="text-destructive">AI không đọc được tài liệu này (chỉ giảng viên thấy dòng này)</span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <Loader2 className="size-3 animate-spin" aria-hidden /> AI đang đọc tài liệu, bạn vẫn xem được ngay
                      </span>
                    )}
                  </p>
                </div>
                {d.status === "pending" || d.status === "processing" ? <Badge tone="primary">Đang xử lý</Badge> : null}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-pressed={open}
                    aria-label={`${open ? "Ẩn" : "Xem"} ${d.title}`}
                    loading={busy === d.source_id}
                    loadingText="Đang mở…"
                    onClick={() => void view(d)}
                  >
                    {open ? <EyeOff /> : <Eye />} {open ? "Ẩn" : "Xem"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label={`Tải xuống ${d.title}`}
                    onClick={() => downloadSourcePdf(d.source_id).catch((err) => toast.error(errorMessage(err)))}
                  >
                    <Download /> Tải xuống
                  </Button>
                </div>
              </div>
              {open ? (
                <div className="mt-3">
                  <iframe title={`Tài liệu: ${d.title}`} src={viewing.url} className="h-[75vh] w-full rounded-md border bg-white" />
                  <a
                    href={viewing.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-sm text-primary hover:underline"
                  >
                    <ExternalLink className="size-4" aria-hidden /> Không hiện? Mở trong thẻ mới
                  </a>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
