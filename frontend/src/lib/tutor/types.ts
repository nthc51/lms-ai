import type { components } from "@/lib/api/schema";

export type Citation = components["schemas"]["Citation"];

/** Một nguồn trong event `sources` (có thêm phần hiển thị so với Citation). */
export type Source = Citation & { lesson_title: string; heading_path: string; snippet: string };

export type ChatStatus = "streaming" | "done" | "error" | "stopped";

export type ChatMessage = {
  id: string; // id tạm "local-…" cho tới khi nhận `done`
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  sources: Source[];
  refused: boolean;
  truncated: boolean;
  feedback: number | null;
  status: ChatStatus;
  error?: string;
};
