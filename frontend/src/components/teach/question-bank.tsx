"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ListChecks, Loader2, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { quizKeys, useGenerateQuestions, useJob, useLessonQuestions, useReviewQuestion } from "@/lib/quiz/queries";
import type { Question } from "@/lib/quiz/types";
import { cn } from "@/lib/utils";
import { QuestionCard, type ReviewAction } from "./question-card";

const TABS = [
  { key: "pending", label: "Chờ duyệt", match: (q: Question) => q.review_status === "pending" },
  { key: "approved", label: "Đã duyệt", match: (q: Question) => q.review_status === "approved" || q.review_status === "edited" },
  { key: "rejected", label: "Đã loại", match: (q: Question) => q.review_status === "rejected" },
] as const;

const MIXES = {
  balanced: { label: "Cân bằng", value: { easy: 0.3, medium: 0.5, hard: 0.2 } },
  easier: { label: "Dễ hơn", value: { easy: 0.5, medium: 0.4, hard: 0.1 } },
  harder: { label: "Khó hơn", value: { easy: 0.1, medium: 0.4, hard: 0.5 } },
} as const;

const UNDO_MS = 5000;

/** Ngân hàng câu hỏi của một bài: sinh bằng AI (job nền) và duyệt / sửa / loại từng câu. */
export function QuestionBank({ lessonId }: { lessonId: string }) {
  const questions = useLessonQuestions(lessonId, "all");
  const review = useReviewQuestion(lessonId);
  const [tab, setTab] = React.useState<(typeof TABS)[number]["key"]>("pending");
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [hidden, setHidden] = React.useState<Set<string>>(new Set()); // đang chờ 5 giây để "Hoàn tác" loại
  const timers = React.useRef(new Map<string, number>());

  const send = React.useCallback(
    async (id: string, a: ReviewAction) => {
      setBusyId(id);
      try {
        await review.mutateAsync({ id, body: a });
      } finally {
        setBusyId(null);
      }
    },
    [review],
  );

  // Loại: ẩn ngay, đợi 5 giây cho "Hoàn tác" rồi mới gửi (design-system §5.3).
  const rejectWithUndo = React.useCallback(
    (q: Question) => {
      setHidden((s) => new Set(s).add(q.id));
      const unhide = () =>
        setHidden((s) => {
          const next = new Set(s);
          next.delete(q.id);
          return next;
        });
      const timer = window.setTimeout(async () => {
        timers.current.delete(q.id);
        try {
          await send(q.id, { action: "reject" });
        } catch (err) {
          toast.error(errorMessage(err));
        } finally {
          unhide();
        }
      }, UNDO_MS);
      timers.current.set(q.id, timer);
      toast("Đã loại câu hỏi", {
        duration: UNDO_MS,
        action: {
          label: "Hoàn tác",
          onClick: () => {
            window.clearTimeout(timers.current.get(q.id));
            timers.current.delete(q.id);
            unhide();
          },
        },
      });
    },
    [send],
  );

  // Rời trang khi còn câu đang chờ hoàn tác: gửi luôn, không để mất thao tác
  React.useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const [id, t] of pending) {
        window.clearTimeout(t);
        void review.mutateAsync({ id, body: { action: "reject" } }).catch(() => undefined);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onReview(q: Question, a: ReviewAction) {
    if (a.action === "reject") return rejectWithUndo(q);
    try {
      await send(q.id, a);
      toast.success(a.action === "edit" ? "Đã lưu và duyệt câu hỏi" : "Đã duyệt");
    } catch (err) {
      if (a.action === "edit") throw err; // form sửa tự hiện lỗi tại chỗ
      toast.error(errorMessage(err));
    }
  }

  const all = (questions.data?.items ?? []).filter((q) => !hidden.has(q.id));
  const current = TABS.find((t) => t.key === tab)!;
  const visible = all.filter(current.match);

  return (
    <div className="space-y-6">
      <GeneratePanel lessonId={lessonId} />

      <div role="tablist" aria-label="Lọc câu hỏi" className="flex gap-1 border-b">
        {TABS.map((t) => {
          const count = all.filter(t.match).length;
          return (
            <button
              key={t.key}
              role="tab"
              type="button"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "-mb-px h-11 border-b-2 border-transparent px-3 text-sm",
                tab === t.key ? "border-primary font-medium text-primary" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label} ({count})
            </button>
          );
        })}
      </div>

      <div role="tabpanel" aria-label={current.label}>
        {questions.isPending ? (
          <div className="space-y-3" aria-busy="true" aria-label="Đang tải câu hỏi">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : questions.isError ? (
          <ErrorState error={questions.error} onRetry={() => questions.refetch()} />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={ListChecks}
            title={tab === "pending" ? "Không có câu nào chờ duyệt. Bấm “Sinh câu hỏi bằng AI” để tạo thêm." : `Chưa có câu nào ${current.label.toLowerCase()}.`}
          />
        ) : (
          <ol className="space-y-4">
            {visible.map((q, i) => (
              <li key={q.id}>
                <QuestionCard q={q} n={i + 1} busy={busyId === q.id} onReview={(a) => onReview(q, a)} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function GeneratePanel({ lessonId }: { lessonId: string }) {
  const qc = useQueryClient();
  const generate = useGenerateQuestions(lessonId);
  const [count, setCount] = React.useState(10);
  const [mix, setMix] = React.useState<keyof typeof MIXES>("balanced");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const job = useJob(jobId);
  const status = job.data?.status;
  const running = !!jobId && status !== "done" && status !== "failed";

  // Job xong → tải lại danh sách và báo số câu chờ duyệt
  const handled = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!jobId || handled.current === jobId || (status !== "done" && status !== "failed")) return;
    handled.current = jobId;
    if (status === "done") {
      void qc.invalidateQueries({ queryKey: quizKeys.questions(lessonId) }).then(() => {
        const items = qc.getQueryData<{ items: Question[] }>(quizKeys.questionList(lessonId, "all"))?.items ?? [];
        toast.success(`AI đã soạn xong. Có ${items.filter((q) => q.review_status === "pending").length} câu chờ duyệt.`);
      });
    }
  }, [jobId, status, lessonId, qc]);

  async function start() {
    try {
      const { job_id } = await generate.mutateAsync({ count, difficulty: MIXES[mix].value });
      setJobId(job_id);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <section aria-labelledby="gen-title" className="rounded-lg border bg-surface p-4">
      <h2 id="gen-title" className="font-semibold">
        Sinh câu hỏi bằng AI
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        AI soạn câu trắc nghiệm từ tài liệu PDF đã xử lý của bài. Câu sinh ra cần bạn duyệt trước khi đưa vào quiz.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="text-sm">
          <span className="mb-1 block font-medium">Số câu</span>
          <select
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            disabled={running}
            className="h-10 rounded-md border bg-surface px-3"
          >
            {[5, 10, 15, 20].map((n) => (
              <option key={n} value={n}>
                {n} câu
              </option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend className="mb-1 text-sm font-medium">Độ khó</legend>
          <div className="inline-flex rounded-md border p-0.5">
            {(Object.keys(MIXES) as (keyof typeof MIXES)[]).map((k) => (
              <label
                key={k}
                className={cn(
                  "flex h-9 cursor-pointer items-center rounded px-3 text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                  mix === k && "bg-primary text-primary-foreground",
                )}
              >
                <input type="radio" name="mix" className="sr-only" checked={mix === k} disabled={running} onChange={() => setMix(k)} />
                {MIXES[k].label}
              </label>
            ))}
          </div>
        </fieldset>
        <Button onClick={start} loading={generate.isPending} loadingText="Đang gửi…" disabled={running}>
          <Sparkles /> Sinh câu hỏi bằng AI
        </Button>
      </div>
      <div aria-live="polite" className="mt-3 text-sm">
        {running ? (
          <p className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> AI đang soạn… (thường mất khoảng 1 phút). Bạn vẫn duyệt các câu khác được.
          </p>
        ) : status === "failed" ? (
          <p role="alert" className="text-destructive">
            {job.data?.error_msg ?? "Không sinh được câu hỏi. Thử lại sau."}
          </p>
        ) : null}
      </div>
    </section>
  );
}
