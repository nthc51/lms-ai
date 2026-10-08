"use client";

import { BookmarkPlus, Download, Pencil, X } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type Artifact, downloadMarkdown, kindLabel, useArtifact, useNoteMutations, useUpdateArtifact } from "@/lib/studio/queries";
import { CitedMarkdown } from "./cited-markdown";
import { FlashcardDeck } from "./flashcard-deck";

/** Khung toàn màn hình mở một tài liệu học: báo cáo (đọc, lưu ghi chú, tải .md, giảng viên sửa) hoặc flashcard. */
export function ArtifactViewer({
  artifactId,
  title,
  canEdit,
  lessonId,
  onOpenChange,
}: {
  artifactId: string | null;
  title: string;
  canEdit: boolean;
  lessonId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const artifact = useArtifact(artifactId);
  return (
    <D.Root open={!!artifactId} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <D.Content
          aria-describedby={undefined}
          className="fixed inset-0 z-50 flex flex-col bg-background md:inset-6 md:rounded-lg md:border md:shadow-lg"
        >
          <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
            <D.Title className="min-w-0 flex-1 truncate font-semibold">{title}</D.Title>
            {artifact.data?.reviewed ? <Badge tone="success">Giảng viên đã duyệt</Badge> : null}
            <D.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Đóng">
                <X />
              </Button>
            </D.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {artifact.isPending ? (
              <div className="mx-auto max-w-3xl space-y-3 p-6" aria-busy="true" aria-label="Đang tải">
                <Skeleton className="h-8 w-1/2" />
                <Skeleton className="h-40 w-full" />
              </div>
            ) : artifact.isError ? (
              <p className="p-6 text-destructive">{errorMessage(artifact.error)}</p>
            ) : artifact.data.kind === "flashcards" ? (
              <FlashcardDeck artifact={artifact.data} canEdit={canEdit} lessonId={lessonId} />
            ) : (
              <Report artifact={artifact.data} title={title} canEdit={canEdit} lessonId={lessonId} />
            )}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

function Report({ artifact, title, canEdit, lessonId }: { artifact: Artifact; title: string; canEdit: boolean; lessonId: string | null }) {
  const notes = useNoteMutations();
  const update = useUpdateArtifact(artifact.id);
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(artifact.content_md);

  async function saveToNotes() {
    try {
      await notes.create.mutateAsync({
        course_id: artifact.course_id,
        lesson_id: artifact.lesson_id,
        title: `${kindLabel(artifact.kind)}: ${title}`.slice(0, 200),
        content_md: artifact.content_md,
        // Lệch plan: NoteIn.citations có kiểu NoteCitation (n: int, quyết định 8e ở Task 6); nguồn của báo cáo luôn có n
        citations: artifact.citations as ({ n: number } & Record<string, unknown>)[],
      });
      toast.success("Đã lưu vào ghi chú");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function saveEdit() {
    try {
      await update.mutateAsync({ content_md: draft });
      setEditing(false);
      toast.success("Đã lưu, bản này được đánh dấu đã duyệt");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-4 md:p-8">
      <div className="mb-6 flex flex-wrap gap-2">
        <Button variant="outline" onClick={saveToNotes} loading={notes.create.isPending} loadingText="Đang lưu…">
          <BookmarkPlus /> Lưu vào ghi chú
        </Button>
        <Button variant="outline" onClick={() => downloadMarkdown(`${kindLabel(artifact.kind)}.md`, artifact.content_md)}>
          <Download /> Tải xuống (.md)
        </Button>
        {canEdit && !editing ? (
          <Button variant="ghost" onClick={() => (setDraft(artifact.content_md), setEditing(true))}>
            <Pencil /> Sửa
          </Button>
        ) : null}
      </div>
      {artifact.stale ? (
        <p className="mb-4 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          Tài liệu của bài đã thay đổi sau khi tạo bản này. Bấm &quot;Tạo bản mới&quot; ở Studio để cập nhật.
        </p>
      ) : null}
      {editing ? (
        <div className="space-y-3">
          <label htmlFor="artifact-edit" className="text-sm font-medium">
            Nội dung (Markdown, giữ các nhãn nguồn [n] nếu còn đúng)
          </label>
          <Textarea id="artifact-edit" value={draft} onChange={(e) => setDraft(e.target.value)} rows={18} className="font-mono text-sm" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(false)}>
              Hủy
            </Button>
            <Button onClick={saveEdit} loading={update.isPending} loadingText="Đang lưu…" disabled={!draft.trim()}>
              Lưu và duyệt
            </Button>
          </div>
        </div>
      ) : (
        <CitedMarkdown content={artifact.content_md} citations={artifact.citations} lessonId={lessonId} />
      )}
    </div>
  );
}
