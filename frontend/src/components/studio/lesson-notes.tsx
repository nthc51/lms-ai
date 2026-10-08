"use client";

import { NotebookPen } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useNoteMutations, useNotes } from "@/lib/studio/queries";
import { CitedMarkdown } from "./cited-markdown";

/** Ghi chú của chính học viên trong bài đang học: viết nhanh, xem lại các câu trả lời AI đã lưu. */
export function LessonNotes({ courseId, lessonId }: { courseId: string; lessonId: string }) {
  const notes = useNotes(courseId, lessonId);
  const mut = useNoteMutations();
  const [title, setTitle] = React.useState("");
  const [content, setContent] = React.useState("");

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await mut.create.mutateAsync({ course_id: courseId, lesson_id: lessonId, title: title.trim(), content_md: content });
      setTitle("");
      setContent("");
      toast.success("Đã lưu ghi chú");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      <form onSubmit={add} className="space-y-2 rounded-lg border p-3">
        <Field id="quick-note-title" label="Ghi chú mới">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Tiêu đề" maxLength={200} />
        </Field>
        <label htmlFor="quick-note-body" className="sr-only">
          Nội dung ghi chú
        </label>
        <Textarea id="quick-note-body" value={content} onChange={(e) => setContent(e.target.value)} rows={3} placeholder="Nội dung (Markdown)" />
        <div className="flex justify-end">
          <Button size="sm" type="submit" disabled={!title.trim()} loading={mut.create.isPending} loadingText="Đang lưu…">
            Lưu
          </Button>
        </div>
      </form>
      {notes.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : notes.isError ? (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(notes.error)}
        </p>
      ) : notes.data.items.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <NotebookPen className="size-4" aria-hidden /> Chưa có ghi chú cho bài này. Bấm &quot;Lưu vào ghi chú&quot; dưới câu trả lời của AI để lưu lại.
        </p>
      ) : (
        <ul className="space-y-3">
          {notes.data.items.map((n) => (
            <li key={n.id} className="rounded-lg border bg-surface p-3">
              <h3 className="font-medium">{n.title}</h3>
              {n.status === "generating" ? (
                <p className="text-sm text-muted-foreground">AI đang tổng hợp…</p>
              ) : (
                <CitedMarkdown content={n.content_md} citations={n.citations} lessonId={lessonId} className="mt-1 text-sm [--reader-size:14px]" />
              )}
            </li>
          ))}
        </ul>
      )}
      <Button asChild variant="link">
        <Link href="/notes">Mở sổ ghi chú đầy đủ</Link>
      </Button>
    </div>
  );
}
