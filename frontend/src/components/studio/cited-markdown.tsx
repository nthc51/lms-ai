"use client";

import { Markdown } from "@/components/content/markdown";
import { CitationChip } from "@/components/tutor/citation-chip";
import { linkCitations } from "@/lib/tutor/citations";
import type { Source } from "@/lib/tutor/types";

/** Markdown có trích nguồn [n] bấm được (báo cáo Studio, ghi chú). citations: bản ghi nguồn đã lưu kèm nội dung. */
export function CitedMarkdown({
  content,
  citations,
  lessonId,
  onOpenLesson,
  className,
}: {
  content: string;
  citations: Record<string, unknown>[];
  lessonId: string | null;
  onOpenLesson?: (id: string) => void;
  className?: string;
}) {
  const sources = citations as unknown as Source[];
  const body = linkCitations(content, new Set(sources.map((s) => s.n)));
  return (
    <Markdown
      className={className}
      components={{
        a: ({ href, children }) => {
          const m = href?.match(/^#cite-(\d+)$/);
          if (!m) return <a href={href}>{children}</a>;
          const n = Number(m[1]);
          return <CitationChip n={n} source={sources.find((s) => s.n === n)} currentLessonId={lessonId} onOpenLesson={onOpenLesson} />;
        },
      }}
    >
      {body}
    </Markdown>
  );
}
