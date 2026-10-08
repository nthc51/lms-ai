"use client";

import { FileText } from "lucide-react";
import { Popover } from "radix-ui";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { openSourcePdf, useChunk } from "@/lib/studio/queries";
import { formatTimestamp } from "@/lib/tutor/citations";
import type { Citation, Source } from "@/lib/tutor/types";

/**
 * Chip [n] trong câu trả lời. Bấm mở thẻ nhỏ: đoạn trích, bài, trang/giây.
 * Nếu nguồn là video của bài đang mở → nút "Tua tới mm:ss"; nguồn là trang PDF → "Mở PDF trang N".
 * Lịch sử chat chỉ lưu số trang (không có đoạn trích): mở thẻ thì tải đoạn tài liệu (AI Studio S5).
 */
export function CitationChip({
  n,
  citation,
  source,
  currentLessonId,
  onSeek,
  onOpenLesson,
}: {
  n: number;
  citation?: Citation;
  source?: Source;
  currentLessonId: string | null;
  onSeek?: (sec: number) => void;
  onOpenLesson?: (lessonId: string) => void;
}) {
  const c = source ?? citation;
  const where = c?.start_sec != null ? `phút ${formatTimestamp(c.start_sec)}` : c?.page_no != null ? `trang ${c.page_no}` : null;
  const [open, setOpen] = React.useState(false);
  // Cần đoạn tài liệu khi thiếu đoạn trích, và cần source_id để mở PDF: tải khi mở thẻ, dùng lại lần sau.
  const chunk = useChunk(c?.chunk_id ?? null, open);
  const snippet = source?.snippet || chunk.data?.content;
  const lessonTitle = source?.lesson_title ?? chunk.data?.lesson_title;
  const headingPath = source?.heading_path || chunk.data?.heading_path;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`Nguồn ${n}${where ? `, ${where}` : ""}`}
          className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border border-accent/50 px-1 align-text-top text-xs font-medium text-accent hover:bg-accent/10"
        >
          {n}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content sideOffset={6} className="z-50 w-72 rounded-md border bg-surface p-3 text-sm shadow-md">
          <p className="font-medium">
            [{n}] {lessonTitle ?? "Tài liệu bài học"}
            {where ? <span className="font-normal text-muted-foreground"> · {where}</span> : null}
          </p>
          {headingPath ? <p className="mt-0.5 text-xs text-muted-foreground">{headingPath}</p> : null}
          {snippet ? (
            <p className="mt-2 line-clamp-6 text-muted-foreground">{snippet}</p>
          ) : chunk.isPending && open ? (
            <Skeleton className="mt-2 h-12 w-full" />
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            {chunk.data && c?.page_no != null && c.start_sec == null ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => openSourcePdf(chunk.data!.source_id, c.page_no).catch((err) => toast.error(errorMessage(err)))}
              >
                <FileText /> Mở PDF trang {c.page_no}
              </Button>
            ) : null}
            {c?.start_sec != null && c.lesson_id === currentLessonId && onSeek ? (
              <Button size="sm" variant="outline" onClick={() => onSeek(c.start_sec!)}>
                Tua tới {formatTimestamp(c.start_sec)}
              </Button>
            ) : null}
            {c && c.lesson_id !== currentLessonId && onOpenLesson ? (
              <Button size="sm" variant="outline" onClick={() => onOpenLesson(c.lesson_id)}>
                Mở bài này
              </Button>
            ) : null}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
