"use client";

import { AlertTriangle, Check, CheckCircle2, Pencil, RotateCcw, X } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { DIFFICULTY_LABEL, type Difficulty, type Question } from "@/lib/quiz/types";
import { cn } from "@/lib/utils";

const STATUS_BADGE = {
  pending: { label: "Chờ duyệt", tone: "accent" },
  approved: { label: "Đã duyệt", tone: "success" },
  edited: { label: "Đã sửa và duyệt", tone: "success" },
  rejected: { label: "Đã loại", tone: "neutral" },
} as const;

export type ReviewAction =
  | { action: "approve" }
  | { action: "reject" }
  | {
      action: "edit";
      stem: string;
      options: { id: string; text: string }[];
      correct_option_id: string;
      explanation: string;
      difficulty: Difficulty;
    };

/**
 * Một câu hỏi trong màn duyệt (design-system §5.3: Duyệt = Chính, Sửa / Loại = Phụ).
 * Hiện đáp án đúng bằng icon + chữ, cảnh báo khi AI tự kiểm tra thấy nghi vấn, và đoạn tài liệu nguồn.
 */
export function QuestionCard({
  q,
  n,
  onReview,
  busy,
}: {
  q: Question;
  n: number;
  onReview: (a: ReviewAction) => Promise<unknown>;
  busy: boolean;
}) {
  const [editing, setEditing] = React.useState(false);
  const status = STATUS_BADGE[q.review_status];

  return (
    <article aria-labelledby={`q-${q.id}`} className="rounded-lg border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium text-muted-foreground">Câu {n}</span>
        <Badge tone={status.tone}>{status.label}</Badge>
        <Badge>{DIFFICULTY_LABEL[q.difficulty]}</Badge>
        <Badge>{q.origin === "ai" ? "AI sinh" : "Thủ công"}</Badge>
        {q.self_check_flag ? (
          <Badge tone="destructive">
            <AlertTriangle className="size-3" aria-hidden /> AI tự kiểm tra thấy nghi vấn
          </Badge>
        ) : null}
      </div>

      {editing ? (
        <EditForm
          q={q}
          onCancel={() => setEditing(false)}
          onSave={async (a) => {
            await onReview(a);
            setEditing(false);
          }}
        />
      ) : (
        <>
          <p id={`q-${q.id}`} className="reader mt-3 font-medium [--reader-size:16px]">
            {q.stem}
          </p>
          <ul className="mt-3 space-y-1.5">
            {q.options.map((o) => {
              const correct = o.id === q.correct_option_id;
              return (
                <li
                  key={o.id}
                  className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm", correct && "border-success/60 bg-success/10")}
                >
                  <span className="font-semibold">{o.id}.</span>
                  <span className="flex-1">{o.text}</span>
                  {correct ? (
                    <span className="flex shrink-0 items-center gap-1 font-medium">
                      <CheckCircle2 className="size-4 text-success" aria-hidden /> Đáp án đúng
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {q.explanation ? <p className="mt-3 text-sm text-muted-foreground">Giải thích: {q.explanation}</p> : null}
          {q.source_excerpt ? (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-primary underline-offset-4 hover:underline">
                Đoạn tài liệu nguồn{q.source_page_no ? ` (trang ${q.source_page_no})` : ""}
              </summary>
              <p className="mt-2 whitespace-pre-line rounded-md bg-muted p-3 text-muted-foreground">{q.source_excerpt}</p>
            </details>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-2">
            {q.review_status === "pending" ? (
              <Button size="sm" className="h-10 md:h-8" loading={busy} loadingText="Đang duyệt…" onClick={() => onReview({ action: "approve" })}>
                <Check /> Duyệt
              </Button>
            ) : null}
            {q.review_status === "rejected" ? (
              <Button size="sm" variant="outline" className="h-10 md:h-8" loading={busy} loadingText="Đang khôi phục…" onClick={() => onReview({ action: "approve" })}>
                <RotateCcw /> Khôi phục và duyệt
              </Button>
            ) : (
              <>
                <Button size="sm" variant="outline" className="h-10 md:h-8" disabled={busy} onClick={() => setEditing(true)}>
                  <Pencil /> Sửa
                </Button>
                <Button size="sm" variant="outline" className="h-10 md:h-8" disabled={busy} onClick={() => onReview({ action: "reject" })}>
                  <X /> Loại
                </Button>
              </>
            )}
          </div>
        </>
      )}
    </article>
  );
}

function EditForm({
  q,
  onCancel,
  onSave,
}: {
  q: Question;
  onCancel: () => void;
  onSave: (a: ReviewAction) => Promise<void>;
}) {
  const [stem, setStem] = React.useState(q.stem);
  const [options, setOptions] = React.useState(q.options.map((o) => ({ ...o })));
  const [correct, setCorrect] = React.useState(q.correct_option_id);
  const [explanation, setExplanation] = React.useState(q.explanation);
  const [difficulty, setDifficulty] = React.useState<Difficulty>(q.difficulty);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await onSave({ action: "edit", stem, options, correct_option_id: correct, explanation, difficulty });
    } catch (err) {
      // 422: luật câu hỏi (đúng 4 lựa chọn khác nhau, đề ≥ 10 ký tự…) — hiện câu backend trả về
      const detail = err instanceof ApiError ? (err.details.errors as { msg: string }[] | undefined)?.[0]?.msg : undefined;
      setError(detail ? `${errorMessage(err)}: ${detail}` : errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-4">
      <Field id={`stem-${q.id}`} label="Đề bài">
        <Textarea rows={3} value={stem} maxLength={1000} onChange={(e) => setStem(e.target.value)} />
      </Field>
      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium">Các lựa chọn (chọn ô tròn ở đáp án đúng)</legend>
        {options.map((o, i) => (
          <div key={o.id} className="flex items-center gap-2">
            <input
              type="radio"
              name={`correct-${q.id}`}
              checked={correct === o.id}
              onChange={() => setCorrect(o.id)}
              aria-label={`Đáp án đúng là ${o.id}`}
              className="size-5 accent-[var(--primary)]"
            />
            <span className="w-5 font-semibold">{o.id}.</span>
            <Input
              aria-label={`Lựa chọn ${o.id}`}
              value={o.text}
              maxLength={300}
              onChange={(e) => setOptions((prev) => prev.map((p, j) => (j === i ? { ...p, text: e.target.value } : p)))}
            />
          </div>
        ))}
      </fieldset>
      <Field id={`exp-${q.id}`} label="Giải thích">
        <Textarea rows={2} value={explanation} maxLength={2000} onChange={(e) => setExplanation(e.target.value)} />
      </Field>
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Độ khó</legend>
        <div className="inline-flex rounded-md border p-0.5">
          {(["easy", "medium", "hard"] as const).map((d) => (
            <label
              key={d}
              className={cn(
                "flex h-9 cursor-pointer items-center rounded px-3 text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                difficulty === d && "bg-primary text-primary-foreground",
              )}
            >
              <input type="radio" name={`diff-${q.id}`} className="sr-only" checked={difficulty === d} onChange={() => setDifficulty(d)} />
              {DIFFICULTY_LABEL[d]}
            </label>
          ))}
        </div>
      </fieldset>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={pending}>
          Hủy
        </Button>
        <Button type="submit" loading={pending} loadingText="Đang lưu…">
          Lưu và duyệt
        </Button>
      </div>
    </form>
  );
}
