"use client";

import { Globe, MoreHorizontal, NotebookPen, Pencil, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type Assignment, useAssignmentMutations, useLessonAssignments } from "@/lib/assignments";
import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";

const MAX_CRITERIA = 8;
/** Một dòng rubric trong form; điểm tối đa giữ dạng chuỗi để xóa trắng ô được khi đang gõ. */
type CriterionDraft = { criterion: string; max_points: string; description: string };
const emptyCriterion = (): CriterionDraft => ({ criterion: "", max_points: "2", description: "" });

/** Bài tập của một bài (B5): tạo/sửa (đề bài, hạn nộp, rubric), xuất bản có xác nhận, xem bài nộp để chấm. */
export function AssignmentManager({ slug, lessonId }: { slug: string; lessonId: string }) {
  const list = useLessonAssignments(lessonId);
  const mut = useAssignmentMutations();
  const [editing, setEditing] = React.useState<Assignment | "new" | null>(null);
  const [publishing, setPublishing] = React.useState<Assignment | null>(null);
  const [deleting, setDeleting] = React.useState<Assignment | null>(null);

  const createButton = (
    <Button onClick={() => setEditing("new")}>
      <Plus /> Tạo bài tập
    </Button>
  );

  return (
    <section aria-labelledby="assignment-title" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="assignment-title" className="text-lg font-semibold">
          Bài tập của bài
        </h2>
        {list.data?.items.length ? createButton : null}
      </div>

      {list.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.items.length === 0 ? (
        <EmptyState
          icon={NotebookPen}
          title="Bài này chưa có bài tập. Ra đề kèm rubric, AI sẽ gợi ý điểm từng tiêu chí, bạn xác nhận điểm cuối."
          action={createButton}
        />
      ) : (
        <ul className="space-y-3">
          {list.data.items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{a.title}</p>
                <p className="text-sm text-muted-foreground">
                  {a.rubric.length} tiêu chí · {a.max_total} điểm ·{" "}
                  {a.due_at ? `hạn ${formatDateTime(a.due_at)}` : "không có hạn nộp"} · {a.submission_count ?? 0} bài nộp
                  {a.to_review ? ` · ${a.to_review} chờ xác nhận` : ""}
                </p>
              </div>
              {a.status === "published" ? <Badge tone="success">Đã xuất bản</Badge> : <Badge>Nháp</Badge>}
              <Button asChild variant="outline" size="sm" className="h-10 md:h-8">
                <Link href={`/teach/${slug}/lessons/${lessonId}/assignments/${a.id}`}>Bài nộp</Link>
              </Button>
              {a.status === "draft" ? (
                <Button size="sm" className="h-10 md:h-8" onClick={() => setPublishing(a)}>
                  <Globe /> Xuất bản
                </Button>
              ) : null}
              <Menu>
                <MenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label={`Thao tác với bài tập ${a.title}`}>
                    <MoreHorizontal />
                  </Button>
                </MenuTrigger>
                <MenuContent>
                  <MenuItem onSelect={() => setEditing(a)}>
                    <Pencil /> Sửa
                  </MenuItem>
                  <MenuItem destructive disabled={!!a.submission_count} onSelect={() => setDeleting(a)}>
                    <Trash2 /> Xóa bài tập
                  </MenuItem>
                </MenuContent>
              </Menu>
            </li>
          ))}
        </ul>
      )}

      {editing ? (
        <AssignmentDialog lessonId={lessonId} assignment={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      ) : null}

      <ConfirmDialog
        open={!!publishing}
        onOpenChange={(o) => !o && setPublishing(null)}
        title={`Xuất bản “${publishing?.title}”?`}
        description="Học viên đã đăng ký sẽ thấy bài tập, nộp được bài và nhận thông báo."
        confirmLabel="Xuất bản"
        pendingLabel="Đang xuất bản…"
        onConfirm={async () => {
          try {
            await mut.publish.mutateAsync(publishing!.id);
            toast.success("Đã xuất bản bài tập");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        destructive
        title={`Xóa bài tập “${deleting?.title}”?`}
        description="Bài tập chưa có bài nộp nào nên xóa được. Không khôi phục được."
        confirmLabel="Xóa"
        pendingLabel="Đang xóa…"
        onConfirm={async () => {
          try {
            await mut.remove.mutateAsync(deleting!.id);
            toast.success("Đã xóa bài tập");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </section>
  );
}

function AssignmentDialog({ lessonId, assignment, onClose }: { lessonId: string; assignment: Assignment | null; onClose: () => void }) {
  const mut = useAssignmentMutations();
  const locked = !!assignment?.submission_count; // đã có bài nộp: không đổi rubric được nữa
  const [title, setTitle] = React.useState(assignment?.title ?? "");
  const [instructions, setInstructions] = React.useState(assignment?.instructions ?? "");
  // chốt lúc mở hộp: bài tập được tải lại trong lúc đang sửa cũng không làm lệch phép so "đã đổi hạn nộp chưa"
  const [initialDue] = React.useState(() => (assignment?.due_at ? toLocalInput(assignment.due_at) : ""));
  const [due, setDue] = React.useState(initialDue);
  const [rubric, setRubric] = React.useState<CriterionDraft[]>(
    assignment
      ? assignment.rubric.map(({ criterion, max_points, description }) => ({
          criterion,
          max_points: String(max_points),
          description: description ?? "",
        }))
      : [emptyCriterion()],
  );
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);
  const total = rubric.reduce((n, r) => n + (Number(r.max_points) || 0), 0);

  const setItem = (i: number, patch: Partial<CriterionDraft>) => setRubric((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return setError("Nhập tiêu đề bài tập");
    if (!instructions.trim()) return setError("Nhập đề bài");
    if (rubric.some((r) => !r.criterion.trim())) return setError("Mỗi tiêu chí cần có tên");
    const points = rubric.map((r) => Number(r.max_points.trim() || NaN));
    if (points.some((p) => !Number.isInteger(p) || p < 1 || p > 100))
      return setError("Điểm tối đa mỗi tiêu chí là số nguyên từ 1 đến 100");
    setPending(true);
    setError(null);
    const items = rubric.map((r, i) => ({ criterion: r.criterion.trim(), max_points: points[i], description: r.description }));
    const dueAt = due ? fromLocalInput(due) : null;
    try {
      if (assignment)
        await mut.update.mutateAsync({
          id: assignment.id,
          body: {
            title: title.trim(),
            instructions: instructions.trim(),
            // chỉ gửi hạn nộp khi đã đổi: ô datetime-local bỏ phần giây, gửi lại sẽ làm 23:59:59 thành 23:59:00
            ...(due !== initialDue ? { due_at: dueAt } : {}),
            ...(locked ? {} : { rubric: items }),
          },
        });
      else
        await mut.create.mutateAsync({
          lesson_id: lessonId,
          title: title.trim(),
          instructions: instructions.trim(),
          due_at: dueAt,
          rubric: items,
        });
      toast.success(assignment ? "Đã lưu bài tập" : "Đã tạo bài tập (nháp)");
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={assignment ? "Sửa bài tập" : "Tạo bài tập"}
        description="Bài tập ở dạng nháp cho tới khi bạn xuất bản. AI chấm gợi ý theo đúng rubric này."
        className="max-h-[90dvh] max-w-2xl overflow-y-auto"
      >
        {/* noValidate: báo lỗi bằng câu tiếng Việt của mình thay vì bong bóng mặc định của trình duyệt */}
        <form onSubmit={submit} noValidate className="space-y-4">
          <Field id="as-title" label="Tiêu đề">
            <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus />
          </Field>
          <Field id="as-instructions" label="Đề bài" hint="Hỗ trợ Markdown và công thức $...$">
            <Textarea rows={6} value={instructions} maxLength={20000} onChange={(e) => setInstructions(e.target.value)} />
          </Field>
          <Field id="as-due" label="Hạn nộp" hint="Để trống nếu không có hạn">
            <Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
          </Field>
          <fieldset className="space-y-3">
            <legend className="mb-1 text-sm font-medium">
              Rubric ({rubric.length} tiêu chí · tổng {total} điểm)
            </legend>
            {locked ? (
              <p className="text-sm text-muted-foreground">Đã có bài nộp nên không đổi được rubric (điểm các bài đã chấm dựa trên rubric này).</p>
            ) : null}
            {rubric.map((r, i) => (
              <div key={i} className="grid gap-2 rounded-md border p-3 sm:grid-cols-[minmax(0,1fr)_96px_auto]">
                <Field id={`as-c${i}`} label={`Tiêu chí ${i + 1}`}>
                  <Input value={r.criterion} maxLength={200} disabled={locked} onChange={(e) => setItem(i, { criterion: e.target.value })} />
                </Field>
                <Field id={`as-p${i}`} label="Điểm tối đa">
                  <Input
                    type="number"
                    min={1}
                    max={100}
                    value={r.max_points}
                    disabled={locked}
                    onChange={(e) => setItem(i, { max_points: e.target.value })}
                  />
                </Field>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="self-end"
                  aria-label={`Bỏ tiêu chí ${i + 1}`}
                  disabled={locked || rubric.length === 1}
                  onClick={() => setRubric((rs) => rs.filter((_, j) => j !== i))}
                >
                  <X />
                </Button>
                <div className="sm:col-span-3">
                  <Field id={`as-d${i}`} label="Thế nào là đạt điểm tối đa">
                    <Input
                      value={r.description ?? ""}
                      maxLength={1000}
                      disabled={locked}
                      onChange={(e) => setItem(i, { description: e.target.value })}
                    />
                  </Field>
                </div>
              </div>
            ))}
            {!locked && rubric.length < MAX_CRITERIA ? (
              <Button type="button" variant="outline" size="sm" onClick={() => setRubric((rs) => [...rs, emptyCriterion()])}>
                <Plus /> Thêm tiêu chí
              </Button>
            ) : null}
          </fieldset>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Hủy
            </Button>
            <Button type="submit" loading={pending} loadingText="Đang lưu…">
              {assignment ? "Lưu" : "Tạo bài tập"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
