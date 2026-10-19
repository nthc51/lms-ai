"use client";

import { MessageSquare, Reply, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type Comment, useDeleteComment, useLessonComments, usePostComment } from "@/lib/discussion";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const MAX_LEN = 2000;

/** Ô viết bình luận/trả lời: Ctrl+Enter để gửi, đếm ký tự khi gần chạm giới hạn. */
function CommentForm({
  id,
  label,
  placeholder,
  submitLabel,
  autoFocus = false,
  onSubmit,
  onCancel,
}: {
  id: string;
  label: string;
  placeholder: string;
  submitLabel: string;
  autoFocus?: boolean;
  onSubmit: (body: string) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const [body, setBody] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const text = body.trim();

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!text || pending) return;
    setPending(true);
    try {
      await onSubmit(text);
      setBody("");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Textarea
        id={id}
        rows={3}
        maxLength={MAX_LEN}
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void submit();
          if (e.key === "Escape" && onCancel) onCancel();
        }}
      />
      <div className="flex flex-wrap items-center justify-end gap-2">
        {body.length > MAX_LEN - 200 ? (
          <span className="mr-auto text-xs tabular-nums text-muted-foreground">
            {body.length}/{MAX_LEN}
          </span>
        ) : null}
        {onCancel ? (
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Hủy
          </Button>
        ) : null}
        <Button type="submit" size="sm" disabled={!text} loading={pending} loadingText="Đang gửi">
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

function Author({ c }: { c: Comment }) {
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
      <span className="font-semibold">{c.author_name}</span>
      {c.is_course_teacher ? (
        <span className="bg-field-1 px-1.5 py-px text-xs font-semibold text-foreground">Giảng viên</span>
      ) : c.author_role === "admin" ? (
        <span className="bg-field-2 px-1.5 py-px text-xs font-semibold text-foreground">Quản trị</span>
      ) : null}
      <time dateTime={c.created_at} className="text-xs text-muted-foreground">
        {timeAgo(c.created_at)}
      </time>
    </p>
  );
}

function CommentBody({ c }: { c: Comment }) {
  if (c.deleted) return <p className="mt-1 text-sm italic text-muted-foreground">Bình luận đã bị xóa.</p>;
  return <p className="mt-1 whitespace-pre-line break-words text-[15px] leading-relaxed">{c.body}</p>;
}

function CommentThread({
  c,
  lessonId,
  onDelete,
}: {
  c: Comment;
  lessonId: string;
  onDelete: (c: Comment) => void;
}) {
  const [replying, setReplying] = React.useState(false);
  const post = usePostComment(lessonId);
  return (
    <li className="bg-surface p-4 md:p-5">
      <Author c={c} />
      <CommentBody c={c} />
      {!c.deleted ? (
        <div className="mt-2 flex gap-1">
          <Button variant="ghost" size="sm" aria-expanded={replying} onClick={() => setReplying((v) => !v)}>
            <Reply /> Trả lời
          </Button>
          {c.can_delete ? (
            <Button variant="ghost" size="sm" onClick={() => onDelete(c)} aria-label={`Xóa bình luận của ${c.author_name}`}>
              <Trash2 /> Xóa
            </Button>
          ) : null}
        </div>
      ) : null}

      {c.replies.length > 0 || replying ? (
        <div className="mt-3 border-l-2 border-field-1 pl-4">
          {c.replies.length > 0 ? (
            <ul className="flex flex-col gap-4" aria-label={`Trả lời cho ${c.author_name}`}>
              {c.replies.map((r) => (
                <li key={r.id}>
                  <Author c={r} />
                  <CommentBody c={r} />
                  {r.can_delete && !r.deleted ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-1"
                      onClick={() => onDelete(r)}
                      aria-label={`Xóa trả lời của ${r.author_name}`}
                    >
                      <Trash2 /> Xóa
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          {replying ? (
            <div className={cn(c.replies.length > 0 && "mt-4")}>
              <CommentForm
                id={`reply-${c.id}`}
                label={`Trả lời ${c.author_name}`}
                placeholder={`Trả lời ${c.author_name}…`}
                submitLabel="Gửi trả lời"
                autoFocus
                onCancel={() => setReplying(false)}
                onSubmit={async (body) => {
                  await post.mutateAsync({ body, parent_id: c.id });
                  setReplying(false);
                }}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/**
 * Thảo luận dưới bài học (B4): học viên hỏi, giảng viên và bạn cùng khóa trả lời (một cấp). Giảng viên được báo
 * khi có câu hỏi mới, người hỏi được báo khi có trả lời (qua chuông thông báo). Liên kết `#thao-luan` cuộn tới đây.
 */
export function LessonDiscussion({ lessonId }: { lessonId: string }) {
  const comments = useLessonComments(lessonId);
  const post = usePostComment(lessonId);
  const del = useDeleteComment(lessonId);
  const [toDelete, setToDelete] = React.useState<Comment | null>(null);
  const ref = React.useRef<HTMLElement>(null);

  // Mở từ thông báo (…#thao-luan): đợi danh sách tải xong rồi mới cuộn, để vị trí không bị xô khi nội dung hiện ra
  const loaded = comments.isSuccess;
  React.useEffect(() => {
    if (loaded && window.location.hash === "#thao-luan") ref.current?.scrollIntoView({ block: "start" });
  }, [loaded]);

  const items = comments.data?.pages.flatMap((p) => p.items) ?? [];
  const total = comments.data?.pages[0]?.total ?? 0;

  return (
    <section id="thao-luan" ref={ref} aria-labelledby="h-thao-luan" className="mt-12 scroll-mt-20">
      <h2 id="h-thao-luan" className="mb-4 flex items-center gap-2 text-xl font-semibold">
        <MessageSquare className="size-5" aria-hidden /> Thảo luận{total ? ` · ${total}` : ""}
      </h2>
      <CommentForm
        id="new-comment"
        label="Đặt câu hỏi hoặc chia sẻ về bài này"
        placeholder="Bạn chưa hiểu chỗ nào trong bài? Hỏi ở đây, giảng viên sẽ được báo."
        submitLabel="Gửi"
        onSubmit={(body) => post.mutateAsync({ body })}
      />

      <div className="mt-6" aria-live="polite" aria-busy={comments.isFetching}>
        {comments.isPending ? (
          <div className="flex flex-col gap-1.5">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : comments.isError ? (
          <p className="text-sm text-muted-foreground">
            Chưa tải được thảo luận.{" "}
            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => comments.refetch()}>
              Thử lại
            </Button>
          </p>
        ) : items.length === 0 ? (
          <p className="bg-surface p-5 text-sm text-muted-foreground">Chưa có thảo luận nào. Hãy là người đầu tiên đặt câu hỏi.</p>
        ) : (
          <>
            <ul className="flex flex-col gap-1.5">
              {items.map((c) => (
                <CommentThread key={c.id} c={c} lessonId={lessonId} onDelete={setToDelete} />
              ))}
            </ul>
            {comments.hasNextPage ? (
              <Button
                variant="outline"
                className="mt-4"
                loading={comments.isFetchingNextPage}
                onClick={() => comments.fetchNextPage()}
              >
                Xem thêm thảo luận
              </Button>
            ) : null}
          </>
        )}
      </div>

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Xóa bình luận?"
        description="Nội dung sẽ được thay bằng “Bình luận đã bị xóa”. Các trả lời bên dưới vẫn được giữ."
        confirmLabel="Xóa"
        pendingLabel="Đang xóa"
        destructive
        onConfirm={async () => {
          if (!toDelete) return;
          try {
            await del.mutateAsync(toDelete.id);
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </section>
  );
}
