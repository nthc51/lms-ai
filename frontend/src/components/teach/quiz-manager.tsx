"use client";

import { ClipboardCheck, Globe, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useLessonQuestions, useLessonQuizzes, useQuiz, useQuizMutations } from "@/lib/quiz/queries";
import { DIFFICULTY_LABEL, type Quiz } from "@/lib/quiz/types";

/** Quiz của một bài: tạo từ các câu đã duyệt, sửa khi còn nháp, xuất bản (có xác nhận), xóa (trong menu ⋯). */
export function QuizManager({ lessonId }: { lessonId: string }) {
  const quizzes = useLessonQuizzes(lessonId);
  const mut = useQuizMutations(lessonId);
  const [editing, setEditing] = React.useState<Quiz | "new" | null>(null);
  const [publishing, setPublishing] = React.useState<Quiz | null>(null);
  const [deleting, setDeleting] = React.useState<Quiz | null>(null);

  const createButton = (
    <Button onClick={() => setEditing("new")}>
      <Plus /> Tạo quiz
    </Button>
  );

  return (
    <section aria-labelledby="quiz-title" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="quiz-title" className="text-lg font-semibold">
          Quiz của bài
        </h2>
        {quizzes.data?.items.length ? createButton : null}
      </div>

      {quizzes.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : quizzes.isError ? (
        <ErrorState error={quizzes.error} onRetry={() => quizzes.refetch()} />
      ) : quizzes.data.items.length === 0 ? (
        <EmptyState icon={ClipboardCheck} title="Bài này chưa có quiz. Tạo quiz từ các câu hỏi đã duyệt." action={createButton} />
      ) : (
        <ul className="space-y-3">
          {quizzes.data.items.map((q) => (
            <li key={q.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{q.title}</p>
                <p className="text-sm text-muted-foreground">
                  {q.question_count} câu · tối đa {q.max_attempts} lượt · đạt từ {q.pass_score}%
                </p>
              </div>
              {q.status === "published" ? <Badge tone="success">Đã xuất bản</Badge> : <Badge>Nháp</Badge>}
              {q.status === "draft" ? (
                <>
                  <Button variant="outline" size="sm" className="h-10 md:h-8" onClick={() => setEditing(q)}>
                    <Pencil /> Sửa
                  </Button>
                  <div className="flex flex-col items-end gap-1">
                    <Button
                      size="sm"
                      className="h-10 md:h-8"
                      disabled={q.question_count === 0}
                      aria-describedby={q.question_count === 0 ? `quiz-publish-hint-${q.id}` : undefined}
                      onClick={() => setPublishing(q)}
                    >
                      <Globe /> Xuất bản
                    </Button>
                    {q.question_count === 0 ? (
                      <p id={`quiz-publish-hint-${q.id}`} className="text-xs text-muted-foreground">
                        Chọn ít nhất 1 câu hỏi để xuất bản
                      </p>
                    ) : null}
                  </div>
                </>
              ) : null}
              {q.status !== "published" ? (
                <Menu>
                  <MenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label={`Thao tác với quiz ${q.title}`}>
                      <MoreHorizontal />
                    </Button>
                  </MenuTrigger>
                  <MenuContent>
                    <MenuItem destructive onSelect={() => setDeleting(q)}>
                      <Trash2 /> Xóa quiz
                    </MenuItem>
                  </MenuContent>
                </Menu>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {editing ? (
        <QuizDialog lessonId={lessonId} quiz={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      ) : null}

      <ConfirmDialog
        open={!!publishing}
        onOpenChange={(o) => !o && setPublishing(null)}
        title={`Xuất bản “${publishing?.title}”?`}
        description="Học viên đã đăng ký sẽ thấy và làm được quiz này. Sau khi xuất bản chỉ đổi được tiêu đề, không thêm bớt câu hỏi."
        confirmLabel="Xuất bản"
        pendingLabel="Đang xuất bản…"
        onConfirm={async () => {
          try {
            await mut.publish.mutateAsync(publishing!.id);
            toast.success("Đã xuất bản quiz");
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
        title={`Xóa quiz “${deleting?.title}”?`}
        description="Xóa quiz nháp này? Hành động không hoàn tác được. Câu hỏi vẫn còn trong ngân hàng câu hỏi của bài."
        confirmLabel="Xóa quiz"
        pendingLabel="Đang xóa…"
        onConfirm={async () => {
          try {
            await mut.remove.mutateAsync(deleting!.id);
            toast.success("Đã xóa quiz");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </section>
  );
}

function QuizDialog({ lessonId, quiz, onClose }: { lessonId: string; quiz: Quiz | null; onClose: () => void }) {
  const mut = useQuizMutations(lessonId);
  const bank = useLessonQuestions(lessonId, "all");
  const detail = useQuiz(quiz?.id ?? "");
  const [title, setTitle] = React.useState(quiz?.title ?? "");
  const [maxAttempts, setMaxAttempts] = React.useState(quiz?.max_attempts ?? 1);
  const [passScore, setPassScore] = React.useState(quiz?.pass_score ?? 50);
  const [selected, setSelected] = React.useState<Set<string> | null>(quiz ? null : new Set());
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  // Sửa quiz: lấy danh sách câu đang có trong quiz làm lựa chọn ban đầu
  const chosen = selected ?? new Set((detail.data?.questions ?? []).map((q) => q.id));
  const approved = (bank.data?.items ?? []).filter((q) => q.review_status === "approved" || q.review_status === "edited");
  const loading = bank.isPending || (!!quiz && detail.isPending);
  const loadError = (quiz && detail.isError ? detail.error : null) ?? (bank.isError ? bank.error : null);

  function toggle(id: string) {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return setError("Nhập tiêu đề quiz");
    setPending(true);
    setError(null);
    const body = { title: title.trim(), max_attempts: maxAttempts, pass_score: passScore, question_ids: [...chosen] };
    try {
      if (quiz) await mut.update.mutateAsync({ id: quiz.id, body });
      else await mut.create.mutateAsync({ lesson_id: lessonId, ...body });
      toast.success(quiz ? "Đã lưu quiz" : "Đã tạo quiz (nháp)");
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={quiz ? "Sửa quiz" : "Tạo quiz"}
        description="Quiz ở dạng nháp cho tới khi bạn xuất bản."
        className="max-h-[90dvh] max-w-2xl overflow-y-auto"
      >
        <form onSubmit={submit} className="space-y-4">
          <Field id="quiz-title-input" label="Tiêu đề">
            <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="quiz-attempts" label="Số lượt làm tối đa" hint="1–20 lượt">
              <Input type="number" min={1} max={20} value={maxAttempts} onChange={(e) => setMaxAttempts(Number(e.target.value))} />
            </Field>
            <Field id="quiz-pass" label="Điểm đạt (%)" hint="0–100">
              <Input type="number" min={0} max={100} step={5} value={passScore} onChange={(e) => setPassScore(Number(e.target.value))} />
            </Field>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">
              Câu hỏi đã duyệt ({chosen.size}/{approved.length} được chọn)
            </legend>
            {loadError ? (
              <div role="alert" className="space-y-2 text-sm text-destructive">
                <p>{errorMessage(loadError)}</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (bank.isError) void bank.refetch();
                    if (quiz && detail.isError) void detail.refetch();
                  }}
                >
                  Thử lại
                </Button>
              </div>
            ) : loading ? (
              <Skeleton className="h-32 w-full" />
            ) : approved.length === 0 ? (
              <p className="text-sm text-muted-foreground">Chưa có câu nào được duyệt. Duyệt câu hỏi ở tab “Câu hỏi” trước.</p>
            ) : (
              <ul className="max-h-72 space-y-1 overflow-y-auto rounded-md border p-2">
                {approved.map((q) => (
                  <li key={q.id}>
                    <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded px-2 py-2 hover:bg-muted">
                      <input type="checkbox" checked={chosen.has(q.id)} onChange={() => toggle(q.id)} className="mt-1 size-4 accent-[var(--primary)]" />
                      <span className="flex-1 text-sm">{q.stem}</span>
                      <Badge>{DIFFICULTY_LABEL[q.difficulty]}</Badge>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              Hủy
            </Button>
            <Button type="submit" loading={pending} loadingText="Đang lưu…" disabled={!!loadError}>
              {quiz ? "Lưu quiz" : "Tạo quiz"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
