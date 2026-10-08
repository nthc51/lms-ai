"use client";

import { NotebookPen, Sparkles, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { CitedMarkdown } from "@/components/studio/cited-markdown";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { RequireAuth } from "@/lib/auth/require-auth";
import { type Note, useNoteMutations, useNotes } from "@/lib/studio/queries";

const fmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

export default function NotesPage() {
  return (
    <RequireAuth>
      <Notes />
    </RequireAuth>
  );
}

/** Sổ ghi chú: mọi ghi chú của mình (mới sửa trước); chọn nhiều ghi chú cùng khóa để AI gộp thành đề cương. */
function Notes() {
  const notes = useNotes(null);
  const mut = useNoteMutations();
  const [selected, setSelected] = React.useState<string[]>([]);
  const [editing, setEditing] = React.useState<Note | null>(null);

  const items = notes.data?.items ?? [];
  const chosen = items.filter((n) => selected.includes(n.id));
  const sameCourse = chosen.length > 0 && chosen.every((n) => n.course_id === chosen[0].course_id);

  async function synthesize() {
    try {
      await mut.synthesize.mutateAsync({ note_ids: selected });
      setSelected([]);
      toast.success("AI đang tổng hợp đề cương, ghi chú mới sẽ hiện ở đầu danh sách");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Ghi chú của tôi"
        actions={
          selected.length > 0 ? (
            <Button onClick={synthesize} disabled={!sameCourse} loading={mut.synthesize.isPending} loadingText="Đang gửi…">
              <Sparkles /> Tạo đề cương từ {selected.length} ghi chú
            </Button>
          ) : null
        }
      >
        Lưu câu trả lời của AI, tự ghi chú, rồi chọn nhiều ghi chú để AI gộp thành đề cương ôn tập.
      </PageHeader>
      {selected.length > 0 && !sameCourse ? (
        <p role="status" className="mb-4 text-sm text-destructive">
          Chỉ gộp được các ghi chú của cùng một khóa học.
        </p>
      ) : null}
      {notes.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : notes.isError ? (
        <ErrorState error={notes.error} onRetry={() => notes.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={NotebookPen} title="Chưa có ghi chú nào. Trong bài học, bấm biểu tượng lưu dưới câu trả lời của AI để bắt đầu." />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {items.map((n) => (
            <li key={n.id} className="flex flex-col rounded-lg border bg-surface p-4">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1 size-4"
                  aria-label={`Chọn ghi chú ${n.title}`}
                  checked={selected.includes(n.id)}
                  disabled={n.status !== "ready"}
                  onChange={(e) => setSelected((s) => (e.target.checked ? [...s, n.id] : s.filter((x) => x !== n.id)))}
                />
                <div className="min-w-0 flex-1">
                  <h2 className="font-semibold">{n.title}</h2>
                  <p className="text-xs text-muted-foreground">Sửa lúc {fmt.format(new Date(n.updated_at))}</p>
                </div>
                {n.status === "generating" ? <Badge tone="accent">AI đang tổng hợp…</Badge> : null}
                {n.status === "failed" ? <Badge tone="destructive">Lỗi</Badge> : null}
              </div>
              <div className="mt-2 line-clamp-6 text-sm">
                <CitedMarkdown content={n.content_md} citations={n.citations} lessonId={n.lesson_id} className="[--reader-size:14px]" />
              </div>
              <div className="mt-auto flex justify-end pt-3">
                <Button size="sm" variant="outline" onClick={() => setEditing(n)} disabled={n.status === "generating"} aria-label={`Sửa ${n.title}`}>
                  Sửa
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing ? <NoteEditor key={editing.id} note={editing} onClose={() => setEditing(null)} /> : null}
    </>
  );
}

function NoteEditor({ note, onClose }: { note: Note; onClose: () => void }) {
  const mut = useNoteMutations();
  const [title, setTitle] = React.useState(note.title);
  const [content, setContent] = React.useState(note.content_md);
  const [confirm, setConfirm] = React.useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await mut.update.mutateAsync({ id: note.id, title: title.trim(), content_md: content });
      toast.success("Đã lưu ghi chú");
      onClose();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Sửa ghi chú" className="max-w-2xl">
        <form onSubmit={save} className="space-y-4">
          <Field id="note-title" label="Tiêu đề">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </Field>
          <Field id="note-content" label="Nội dung (Markdown)" hint="Xóa nhãn [n] thì nguồn tương ứng cũng bị bỏ.">
            <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={12} />
          </Field>
          <div className="flex justify-between gap-2">
            <Button type="button" variant="destructive-outline" onClick={() => setConfirm(true)}>
              <Trash2 /> Xóa
            </Button>
            <Button type="submit" disabled={!title.trim()} loading={mut.update.isPending} loadingText="Đang lưu…">
              Lưu
            </Button>
          </div>
        </form>
        <ConfirmDialog
          open={confirm}
          onOpenChange={setConfirm}
          destructive
          title="Xóa ghi chú này?"
          description="Ghi chú bị xóa vĩnh viễn."
          confirmLabel="Xóa ghi chú"
          pendingLabel="Đang xóa…"
          onConfirm={async () => {
            try {
              await mut.remove.mutateAsync(note.id);
              toast.success("Đã xóa ghi chú");
              onClose();
            } catch (err) {
              toast.error(errorMessage(err));
              throw err;
            }
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
