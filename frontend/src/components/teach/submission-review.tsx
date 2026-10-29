"use client";

import { AlertTriangle, ArrowLeft, Bot, FileText, Loader2, RotateCcw } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";
import {
  type Assignment,
  SUBMISSION_STATUS_LABEL,
  type SubmissionDetail,
  type SubmissionStatus,
  useAssignment,
  useGradeMutations,
  useSubmission,
  useSubmissions,
} from "@/lib/assignments";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS: [SubmissionStatus | "all", string][] = [
  ["all", "Tất cả"],
  ["ai_graded", "Chờ xác nhận"],
  ["ai_failed", "AI lỗi"],
  ["submitted", "AI đang chấm"],
  ["graded", "Đã chấm"],
];

const STATUS_TONE: Record<SubmissionStatus, "neutral" | "accent" | "destructive" | "success"> = {
  submitted: "neutral",
  ai_graded: "accent",
  ai_failed: "destructive",
  graded: "success",
};

/**
 * Chấm bài tập (B5): danh sách bài nộp bên trái (bài chờ xác nhận lên trước), bài đang chọn bên phải với bài làm,
 * điểm AI gợi ý từng tiêu chí (kèm câu trích làm bằng chứng) và ô điểm của giảng viên. Bài chọn nằm trên URL (?bai=)
 * để thông báo "bài nộp mới" mở thẳng đúng bài.
 */
export function SubmissionReview({ slug, lessonId, assignmentId }: { slug: string; lessonId: string; assignmentId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selected = params.get("bai");
  const assignment = useAssignment(assignmentId);
  const [status, setStatus] = React.useState<SubmissionStatus | "all">("all");
  const [page, setPage] = React.useState(1);
  const list = useSubmissions(assignmentId, status, page);
  const select = (id: string) => router.replace(`${pathname}?bai=${id}`, { scroll: false });

  return (
    <div className="space-y-4">
      <Link
        href={`/teach/${slug}/lessons/${lessonId}/assignments`}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden /> Bài tập của bài
      </Link>
      {assignment.isError ? (
        <ErrorState error={assignment.error} onRetry={() => assignment.refetch()} />
      ) : assignment.data ? (
        <div>
          <h2 className="text-lg font-semibold">{assignment.data.title}</h2>
          <p className="text-sm text-muted-foreground">
            {assignment.data.submission_count ?? 0} bài nộp · {assignment.data.to_review ?? 0} chờ xác nhận ·{" "}
            {assignment.data.due_at ? `hạn ${formatDateTime(assignment.data.due_at)}` : "không có hạn nộp"}
          </p>
        </div>
      ) : (
        <Skeleton className="h-12 w-2/3" />
      )}

      <div role="group" aria-label="Lọc bài nộp" className="flex flex-wrap gap-1.5">
        {FILTERS.map(([key, label]) => (
          <Button
            key={key}
            size="sm"
            variant={status === key ? "default" : "outline"}
            aria-pressed={status === key}
            onClick={() => {
              setStatus(key);
              setPage(1);
            }}
          >
            {label}
          </Button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div>
          {list.isPending ? (
            <Skeleton className="h-40 w-full" />
          ) : list.isError ? (
            <ErrorState error={list.error} onRetry={() => list.refetch()} />
          ) : list.data.items.length === 0 ? (
            <p className="rounded-lg border bg-surface p-4 text-sm text-muted-foreground">Chưa có bài nộp nào.</p>
          ) : (
            <>
              <ul className="space-y-1.5" aria-label="Bài nộp">
                {list.data.items.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => select(s.id)}
                      aria-current={selected === s.id ? "true" : undefined}
                      className={cn(
                        "w-full rounded-lg border bg-surface p-3 text-left transition-colors duration-150 hover:bg-field-3",
                        selected === s.id && "border-primary",
                      )}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium">{s.student_name}</span>
                        <Badge tone={STATUS_TONE[s.status]}>{SUBMISSION_STATUS_LABEL[s.status]}</Badge>
                      </span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        Nộp {formatDateTime(s.submitted_at)}
                        {s.version > 1 ? ` · lần ${s.version}` : ""}
                        {s.final_total != null ? ` · ${s.final_total} điểm` : s.ai_total != null ? ` · AI gợi ý ${s.ai_total}` : ""}
                        {s.flagged ? ` · ${s.flagged} trích dẫn cần xem` : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {list.data.total > list.data.size ? (
                <div className="mt-3 flex justify-between">
                  <Button size="sm" variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>
                    Trang trước
                  </Button>
                  <Button size="sm" variant="outline" disabled={page * list.data.size >= list.data.total} onClick={() => setPage(page + 1)}>
                    Trang sau
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
        {selected && assignment.data ? (
          <SubmissionPanel id={selected} assignment={assignment.data} />
        ) : selected && assignment.isPending ? (
          <Skeleton className="h-96 w-full" />
        ) : (
          <EmptyState icon={FileText} title="Chọn một bài nộp ở danh sách để xem và chấm." />
        )}
      </div>
    </div>
  );
}

function SubmissionPanel({ id, assignment }: { id: string; assignment: Assignment }) {
  const detail = useSubmission(id);
  if (detail.isPending) return <Skeleton className="h-96 w-full" />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const d = detail.data;
  if (d.assignment_id !== assignment.id)
    return <EmptyState icon={FileText} title="Bài nộp này thuộc bài tập khác. Chọn một bài ở danh sách." />;
  return (
    <section aria-label={`Bài nộp của ${d.student_name}`} className="space-y-4 rounded-lg border bg-surface p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">{d.student_name}</h3>
        <Badge tone={STATUS_TONE[d.status]}>{SUBMISSION_STATUS_LABEL[d.status]}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        Nộp lúc {formatDateTime(d.submitted_at)}
        {d.version > 1 ? ` (lần nộp thứ ${d.version})` : ""}
        {d.graded_at ? ` · chấm lúc ${formatDateTime(d.graded_at)}` : ""}
      </p>
      <div>
        <h4 className="mb-1.5 text-sm font-medium">Bài làm</h4>
        {d.text_content ? (
          <div className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-md border bg-background p-3 text-[15px] leading-relaxed">
            {d.text_content}
          </div>
        ) : null}
        {d.file && d.file_url ? (
          <Button asChild variant="outline" size="sm" className="mt-2">
            <a href={d.file_url} target="_blank" rel="noreferrer">
              <FileText /> Mở file {d.file.name ?? "bài làm"}
            </a>
          </Button>
        ) : null}
      </div>
      {d.status === "submitted" ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" aria-hidden /> AI đang chấm gợi ý, bạn vẫn có thể chấm tay ngay.
        </p>
      ) : null}
      {d.status === "ai_failed" ? (
        <p role="alert" className="flex items-start gap-2 rounded-md border border-destructive/40 p-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {d.ai_error ?? "AI không chấm được bài này."}
        </p>
      ) : null}
      {/* Không gắn key theo trạng thái: AI chấm xong trong lúc giảng viên đang gõ thì không được dựng lại form */}
      <GradeForm key={`${d.id}-${d.version}`} detail={d} assignment={assignment} />
    </section>
  );
}

/** Giá trị điền sẵn: bài đã chấm lấy điểm và nhận xét của giảng viên (nhận xét đã xóa thì để trống, không lấy lại
 * bản AI soạn); chưa chấm thì lấy gợi ý của AI nếu có. */
function prefill(detail: SubmissionDetail, assignment: Assignment) {
  const final = detail.final_scores;
  const ai = detail.ai_result;
  return {
    scores: Object.fromEntries(
      assignment.rubric.map((r) => [r.key, String((final ? final[r.key] : ai?.scores[r.key]?.score) ?? "")]),
    ) as Record<string, string>,
    feedback: final ? (detail.teacher_feedback ?? "") : (ai?.feedback ?? ""),
  };
}

function GradeForm({ detail, assignment }: { detail: SubmissionDetail; assignment: Assignment }) {
  const mut = useGradeMutations(detail.id);
  const ai = detail.ai_result;
  const [scores, setScores] = React.useState(() => prefill(detail, assignment).scores);
  const [feedback, setFeedback] = React.useState(() => prefill(detail, assignment).feedback);
  const [touched, setTouched] = React.useState(false);
  const [seenAi, setSeenAi] = React.useState(ai);
  // Gợi ý AI tới khi form đang mở (AI chấm xong / chấm lại): chỉ điền vào khi giảng viên chưa gõ gì và bài chưa
  // được chấm; đã gõ thì giữ nguyên phần của giảng viên (khối "AI gợi ý" bên dưới vẫn hiện điểm AI để so).
  if (ai !== seenAi) {
    setSeenAi(ai);
    if (ai && !touched && !detail.final_scores) {
      const next = prefill(detail, assignment);
      setScores(next.scores);
      setFeedback(next.feedback);
    }
  }
  const [error, setError] = React.useState<string | null>(null);
  const total = assignment.rubric.reduce((n, r) => n + (Number(scores[r.key]) || 0), 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const parsed: Record<string, number> = {};
    for (const r of assignment.rubric) {
      const raw = scores[r.key]?.trim() ?? "";
      const v = Number(raw);
      if (raw === "" || Number.isNaN(v) || v < 0 || v > r.max_points)
        return setError(`Điểm "${r.criterion}" phải từ 0 đến ${r.max_points}`);
      parsed[r.key] = v;
    }
    setError(null);
    try {
      await mut.grade.mutateAsync({ version: detail.version, scores: parsed, feedback: feedback.trim() || null });
      toast.success("Đã xác nhận điểm, học viên được thông báo");
    } catch (err) {
      // bản mới của học viên được tải lại và form dựng lại theo bản đó, nên báo bằng toast
      if (err instanceof ApiError && err.code === "STALE_VERSION") toast.error(errorMessage(err));
      else setError(errorMessage(err));
    }
  }

  return (
    // noValidate: báo lỗi điểm bằng câu tiếng Việt của mình thay vì bong bóng mặc định của trình duyệt
    <form onSubmit={submit} noValidate className="space-y-4">
      <ol className="space-y-3">
        {assignment.rubric.map((r) => {
          const s = ai?.scores[r.key];
          return (
            <li key={r.key} className="rounded-md border p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {r.criterion} <span className="text-sm font-normal text-muted-foreground">(tối đa {r.max_points})</span>
                  </p>
                  {r.description ? <p className="text-sm text-muted-foreground">{r.description}</p> : null}
                </div>
                <Field id={`score-${r.key}`} label="Điểm">
                  <Input
                    aria-label={`Điểm ${r.criterion}`}
                    type="number"
                    min={0}
                    max={r.max_points}
                    step={0.25}
                    className="w-24"
                    value={scores[r.key]}
                    onChange={(e) => {
                      setTouched(true);
                      setScores((cur) => ({ ...cur, [r.key]: e.target.value }));
                    }}
                  />
                </Field>
              </div>
              {s ? (
                <div className="mt-2 space-y-1.5 rounded-md bg-field-3 p-2.5 text-sm">
                  <p className="flex items-center gap-1.5 font-medium">
                    <Bot className="size-4" aria-hidden /> AI gợi ý {s.score}/{r.max_points}
                  </p>
                  <p>{s.justification}</p>
                  {s.evidence_quote ? (
                    <blockquote className="border-l-2 border-foreground/30 pl-2 italic">“{s.evidence_quote}”</blockquote>
                  ) : null}
                  {!s.evidence_found ? (
                    <p className="flex items-center gap-1.5 font-medium text-destructive">
                      <AlertTriangle className="size-4" aria-hidden />
                      {s.evidence_quote ? "Không tìm thấy câu trích này trong bài làm: kiểm tra lại." : "AI không trích được câu nào làm căn cứ."}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
      <Field id="teacher-feedback" label="Nhận xét cho học viên" hint={ai ? "AI soạn sẵn từ bài làm, bạn sửa lại cho đúng ý" : undefined}>
        <Textarea
          rows={4}
          maxLength={5000}
          value={feedback}
          onChange={(e) => {
            setTouched(true);
            setFeedback(e.target.value);
          }}
        />
      </Field>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-lg font-semibold tabular-nums">
          Tổng: {Math.round(total * 100) / 100}/{assignment.max_total}
        </p>
        <div className="flex flex-wrap gap-2">
          {detail.status === "ai_graded" || detail.status === "ai_failed" ? (
            <Button
              type="button"
              variant="outline"
              loading={mut.regrade.isPending}
              onClick={() =>
                mut.regrade.mutate(undefined, {
                  onSuccess: () => toast.success("Đã gửi AI chấm lại"),
                  onError: (err) => toast.error(errorMessage(err)),
                })
              }
            >
              <RotateCcw /> AI chấm lại
            </Button>
          ) : null}
          <Button type="submit" loading={mut.grade.isPending} loadingText="Đang lưu…">
            {detail.status === "graded" ? "Cập nhật điểm" : "Xác nhận điểm"}
          </Button>
        </div>
      </div>
    </form>
  );
}
