"use client";

import { ArrowLeft, CalendarClock, CheckCircle2, FileText, NotebookPen, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { Markdown } from "@/components/content/markdown";
import { FileDrop } from "@/components/teach/file-drop";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type Assignment, type MySubmission, useAssignment, useSubmit } from "@/lib/assignments";
import { formatDateTime } from "@/lib/format";

const MAX_TEXT = 20_000;

/**
 * Trang bài tập (B5): đề bài, hạn nộp, rubric (để học viên biết được chấm theo gì), ô nộp bài (gõ chữ và/hoặc
 * đính kèm PDF/.txt). Học viên chỉ thấy điểm sau khi giảng viên xác nhận, không thấy điểm AI gợi ý.
 */
export function AssignmentView({ id }: { id: string }) {
  const assignment = useAssignment(id);
  // thời điểm mở trang: đủ để biết đã quá hạn chưa (server vẫn kiểm lại khi nộp)
  const [openedAt] = React.useState(() => Date.now());

  if (assignment.isPending)
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Đang tải bài tập">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (assignment.isError) return <ErrorState error={assignment.error} onRetry={() => assignment.refetch()} />;

  const a = assignment.data;
  const staff = a.submission_count != null;
  const pastDue = !!a.due_at && new Date(a.due_at).getTime() <= openedAt;
  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <Link
        href={`/learn/${a.course_slug}/${a.lesson_id}`}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden /> {a.lesson_title}
      </Link>
      <header>
        <h1 className="text-[clamp(1.75rem,1.3rem+1.6vw,2.5rem)] font-extrabold leading-[1.1] tracking-[-0.03em]">{a.title}</h1>
        <p className="mt-2 flex items-center gap-2 text-muted-foreground">
          <CalendarClock className="size-4" aria-hidden />
          {a.due_at ? `Hạn nộp ${formatDateTime(a.due_at)}${pastDue ? " (đã hết hạn)" : ""}` : "Không có hạn nộp"} · {a.max_total} điểm
        </p>
      </header>

      <section aria-labelledby="as-instructions" className="rounded-lg border bg-surface p-4 md:p-6">
        <h2 id="as-instructions" className="sr-only">
          Đề bài
        </h2>
        <Markdown>{a.instructions}</Markdown>
      </section>

      <section aria-labelledby="as-rubric">
        <h2 id="as-rubric" className="mb-2 text-lg font-semibold">
          Tiêu chí chấm
        </h2>
        <ul className="divide-y rounded-lg border bg-surface">
          {a.rubric.map((r) => (
            <li key={r.key} className="flex gap-4 p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{r.criterion}</p>
                {r.description ? <p className="text-sm text-muted-foreground">{r.description}</p> : null}
              </div>
              <span className="shrink-0 font-semibold tabular-nums">
                {a.my_submission?.final_scores ? `${a.my_submission.final_scores[r.key] ?? 0}/` : ""}
                {r.max_points} điểm
              </span>
            </li>
          ))}
        </ul>
      </section>

      {staff ? (
        <Button asChild>
          <Link href={`/teach/${a.course_slug}/lessons/${a.lesson_id}/assignments/${a.id}`}>Xem bài nộp ({a.submission_count})</Link>
        </Button>
      ) : (
        <SubmissionBox assignment={a} pastDue={pastDue} />
      )}
    </article>
  );
}

function SubmissionBox({ assignment, pastDue }: { assignment: Assignment; pastDue: boolean }) {
  const mine = assignment.my_submission ?? null;
  const [editing, setEditing] = React.useState(false);

  if (mine?.status === "graded") return <Result assignment={assignment} mine={mine} />;
  if (mine && !editing)
    return (
      <section aria-labelledby="as-mine" className="space-y-3 rounded-lg border bg-surface p-4 md:p-6">
        <h2 id="as-mine" className="flex items-center gap-2 text-lg font-semibold">
          <CheckCircle2 className="size-5 text-success" aria-hidden /> Đã nộp bài
        </h2>
        <p className="text-sm text-muted-foreground">
          Nộp lúc {formatDateTime(mine.submitted_at)}
          {mine.version > 1 ? ` (lần ${mine.version})` : ""}. Giảng viên sẽ chấm, bạn nhận thông báo khi có điểm.
        </p>
        <SubmittedContent mine={mine} />
        {!pastDue ? (
          <Button variant="outline" onClick={() => setEditing(true)}>
            Nộp lại
          </Button>
        ) : null}
      </section>
    );
  if (pastDue)
    return <p className="rounded-lg border bg-surface p-4 text-muted-foreground">Đã hết hạn nộp bài.</p>;
  return <SubmitForm assignment={assignment} previous={mine} onDone={() => setEditing(false)} />;
}

function SubmittedContent({ mine }: { mine: MySubmission }) {
  return (
    <>
      {mine.text_content ? (
        <div className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-md border bg-background p-3 text-[15px]">
          {mine.text_content}
        </div>
      ) : null}
      {mine.file ? (
        <p className="flex items-center gap-2 text-sm">
          <FileText className="size-4" aria-hidden /> File đính kèm: {mine.file.name ?? "bài làm"}
        </p>
      ) : null}
    </>
  );
}

function Result({ assignment, mine }: { assignment: Assignment; mine: MySubmission }) {
  return (
    <section aria-labelledby="as-result" className="space-y-4 rounded-lg border bg-surface p-4 md:p-6">
      <h2 id="as-result" className="text-lg font-semibold">
        Kết quả
      </h2>
      <p className="text-4xl font-extrabold tabular-nums">
        {mine.final_total}
        <span className="text-xl font-semibold text-muted-foreground">/{assignment.max_total} điểm</span>
      </p>
      {mine.teacher_feedback ? (
        <div>
          <h3 className="mb-1 text-sm font-medium">Nhận xét của giảng viên</h3>
          <p className="whitespace-pre-wrap">{mine.teacher_feedback}</p>
        </div>
      ) : null}
      <details>
        <summary className="cursor-pointer text-sm font-medium">Bài đã nộp</summary>
        <div className="mt-2 space-y-2">
          <SubmittedContent mine={mine} />
        </div>
      </details>
    </section>
  );
}

function SubmitForm({ assignment, previous, onDone }: { assignment: Assignment; previous: MySubmission | null; onDone: () => void }) {
  const submit = useSubmit(assignment.id);
  const [text, setText] = React.useState(previous?.text_content ?? "");
  const [file, setFile] = React.useState<{ id: string; name: string | null } | null>(
    previous?.file ? { id: previous.file.asset_id, name: previous.file.name } : null,
  );
  const [error, setError] = React.useState<string | null>(null);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() && !file) return setError("Bài làm trống: hãy gõ nội dung hoặc đính kèm file");
    setError(null);
    try {
      await submit.mutateAsync({ text_content: text, asset_id: file?.id ?? null });
      toast.success("Đã nộp bài");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={send} aria-labelledby="as-submit" className="space-y-4 rounded-lg border bg-surface p-4 md:p-6">
      <h2 id="as-submit" className="flex items-center gap-2 text-lg font-semibold">
        <NotebookPen className="size-5" aria-hidden /> {previous ? "Nộp lại bài" : "Nộp bài"}
      </h2>
      <div className="space-y-1.5">
        <label htmlFor="as-text" className="text-sm font-medium">
          Bài làm
        </label>
        <Textarea id="as-text" rows={10} maxLength={MAX_TEXT} value={text} onChange={(e) => setText(e.target.value)} />
        {text.length > MAX_TEXT - 1000 ? (
          <p className="text-xs tabular-nums text-muted-foreground">
            {text.length}/{MAX_TEXT} ký tự
          </p>
        ) : null}
      </div>
      {file ? (
        <p className="flex items-center gap-2 text-sm">
          <FileText className="size-4" aria-hidden /> {file.name ?? "File đính kèm"}
          <Button type="button" variant="ghost" size="sm" onClick={() => setFile(null)} aria-label="Bỏ file đính kèm">
            <X /> Bỏ
          </Button>
        </p>
      ) : (
        <FileDrop
          kind="submission"
          label="Chọn file đính kèm"
          onUploaded={async (id, f) => setFile({ id, name: f.name })}
        />
      )}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        {previous ? (
          <Button type="button" variant="outline" onClick={onDone}>
            Hủy
          </Button>
        ) : null}
        <Button type="submit" loading={submit.isPending} loadingText="Đang nộp…">
          {previous ? "Nộp lại" : "Nộp bài"}
        </Button>
      </div>
    </form>
  );
}
