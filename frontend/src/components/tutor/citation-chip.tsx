"use client";

import { Popover } from "radix-ui";
import { formatTimestamp } from "@/lib/tutor/citations";
import type { Citation, Source } from "@/lib/tutor/types";
import { Button } from "@/components/ui/button";

/**
 * Chip [n] trong câu trả lời. Bấm mở thẻ nhỏ: đoạn trích, bài, trang/giây.
 * Nếu nguồn là video của bài đang mở → nút "Tua tới mm:ss".
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
  return (
    <Popover.Root>
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
            [{n}] {source?.lesson_title ?? "Tài liệu bài học"}
            {where ? <span className="font-normal text-muted-foreground"> · {where}</span> : null}
          </p>
          {source?.heading_path ? <p className="mt-0.5 text-xs text-muted-foreground">{source.heading_path}</p> : null}
          {source?.snippet ? <p className="mt-2 line-clamp-5 text-muted-foreground">{source.snippet}</p> : null}
          <div className="mt-3 flex gap-2">
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
