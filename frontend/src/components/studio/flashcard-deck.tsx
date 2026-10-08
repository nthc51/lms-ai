"use client";

import { Check, ChevronLeft, ChevronRight, Pencil, RotateCcw, X as XIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Progress } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type Artifact, type Card, useReviewCard, useUpdateArtifact } from "@/lib/studio/queries";
import { cn } from "@/lib/utils";
import { CitedMarkdown } from "./cited-markdown";

/**
 * Bộ thẻ: lật xem đáp án, đánh dấu Nhớ / Chưa nhớ, lọc "chỉ thẻ chưa nhớ" để ôn lại.
 * Phím tắt: Space lật, ← → chuyển thẻ, N nhớ, C chưa nhớ. Điện thoại: chạm thẻ để lật.
 */
export function FlashcardDeck({ artifact, canEdit, lessonId }: { artifact: Artifact; canEdit: boolean; lessonId: string | null }) {
  const cards = React.useMemo(() => artifact.cards ?? [], [artifact.cards]);
  const review = useReviewCard(artifact.id);
  const known = new Set(artifact.known_cards);
  const [onlyUnknown, setOnlyUnknown] = React.useState(false);
  // danh sách thẻ đang ôn chốt lúc bật bộ lọc: đánh dấu "Nhớ" không làm thẻ biến mất ngay dưới tay
  const [deck, setDeck] = React.useState<number[]>(() => cards.map((_, i) => i));
  const [pos, setPos] = React.useState(0);
  const [flipped, setFlipped] = React.useState(false);
  const [editing, setEditing] = React.useState(false);

  const current = deck[Math.min(pos, deck.length - 1)];
  const card = current !== undefined ? cards[current] : undefined;

  const go = React.useCallback(
    (d: number) => {
      setPos((p) => Math.min(Math.max(p + d, 0), Math.max(deck.length - 1, 0)));
      setFlipped(false);
    },
    [deck.length],
  );
  const mark = React.useCallback(
    (isKnown: boolean) => {
      if (current === undefined) return;
      review.mutate({ cardNo: current, known: isKnown }, { onError: (err) => toast.error(errorMessage(err)) });
      go(1);
    },
    [current, review, go],
  );

  function toggleFilter() {
    const next = !onlyUnknown;
    setOnlyUnknown(next);
    setDeck(cards.map((_, i) => i).filter((i) => !next || !known.has(i)));
    setPos(0);
    setFlipped(false);
  }

  React.useEffect(() => {
    if (editing) return;
    function onKey(e: KeyboardEvent) {
      // Lệch plan (5d): bỏ qua tổ hợp phím (Ctrl+C sao chép không được đánh dấu "Chưa nhớ")
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === " ") {
        e.preventDefault();
        setFlipped((f) => !f);
      } else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key.toLowerCase() === "n") mark(true);
      else if (e.key.toLowerCase() === "c") mark(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, mark, editing]);

  const knownCount = cards.filter((_, i) => known.has(i)).length;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4 md:p-8">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="tabular-nums">
          Thẻ {deck.length ? pos + 1 : 0}/{deck.length}
        </span>
        <span className="text-muted-foreground tabular-nums">· Đã nhớ {knownCount}/{cards.length}</span>
        <Button size="sm" variant="outline" aria-pressed={onlyUnknown} onClick={toggleFilter} className="ml-auto">
          {onlyUnknown ? "Xem tất cả thẻ" : "Chỉ ôn thẻ chưa nhớ"}
        </Button>
      </div>
      <Progress value={cards.length ? (knownCount / cards.length) * 100 : 0} label={`Đã nhớ ${knownCount} trên ${cards.length} thẻ`} />

      {!card ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
          Bạn đã nhớ hết các thẻ.{" "}
          <Button variant="link" onClick={toggleFilter}>
            Xem lại tất cả
          </Button>
        </div>
      ) : editing ? (
        <CardEditor artifact={artifact} index={current!} onDone={() => setEditing(false)} />
      ) : (
        <>
          <button
            type="button"
            onClick={() => setFlipped((f) => !f)}
            aria-label={flipped ? "Đang xem đáp án, bấm để xem câu hỏi" : "Đang xem câu hỏi, bấm để lật xem đáp án"}
            className={cn(
              "flex min-h-64 w-full flex-col items-center justify-center rounded-xl border-2 p-6 text-center transition-colors md:min-h-80",
              flipped ? "border-accent/60 bg-accent/5" : "bg-surface hover:bg-muted",
            )}
          >
            <span className="mb-3 text-xs uppercase tracking-wide text-muted-foreground">{flipped ? "Đáp án" : "Câu hỏi"}</span>
            <span className="text-xl font-medium">{flipped ? card.back : card.front}</span>
            {known.has(current!) ? <span className="mt-3 text-xs text-muted-foreground">Đã nhớ</span> : null}
          </button>
          {flipped && card.sources?.length ? (
            <div className="text-sm text-muted-foreground">
              <CitedMarkdown
                content={`Nguồn: ${(card.sources ?? []).map((n) => `[${n}]`).join(" ")}`}
                citations={artifact.citations}
                lessonId={lessonId}
              />
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-2 sm:flex sm:justify-center">
            <Button variant="outline" onClick={() => go(-1)} disabled={pos === 0} aria-label="Thẻ trước">
              <ChevronLeft /> Trước
            </Button>
            <Button variant="outline" onClick={() => go(1)} disabled={pos >= deck.length - 1} aria-label="Thẻ sau">
              Sau <ChevronRight />
            </Button>
            <Button variant="outline" onClick={() => mark(false)}>
              <XIcon /> Chưa nhớ
            </Button>
            <Button onClick={() => mark(true)}>
              <Check /> Nhớ rồi
            </Button>
          </div>
          <p className="text-center text-xs text-muted-foreground">Phím tắt: Space lật · ← → chuyển thẻ · N nhớ · C chưa nhớ</p>
          <div className="flex justify-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => (setPos(0), setFlipped(false))}>
              <RotateCcw /> Về thẻ đầu
            </Button>
            {canEdit ? (
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
                <Pencil /> Sửa thẻ này
              </Button>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}

function CardEditor({ artifact, index, onDone }: { artifact: Artifact; index: number; onDone: () => void }) {
  const update = useUpdateArtifact(artifact.id);
  const cards = artifact.cards ?? [];
  const [front, setFront] = React.useState(cards[index].front);
  const [back, setBack] = React.useState(cards[index].back);

  async function save(remove = false) {
    const next: Card[] = remove
      ? cards.filter((_, i) => i !== index)
      : cards.map((c, i) => (i === index ? { ...c, front: front.trim(), back: back.trim() } : c));
    try {
      await update.mutateAsync({ cards: next });
      toast.success(remove ? "Đã xóa thẻ" : "Đã lưu thẻ");
      onDone();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <Field id="card-front" label="Mặt trước (câu hỏi)">
        <Input value={front} onChange={(e) => setFront(e.target.value)} maxLength={300} />
      </Field>
      <Field id="card-back" label="Mặt sau (đáp án)">
        <Textarea value={back} onChange={(e) => setBack(e.target.value)} rows={4} maxLength={800} />
      </Field>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="destructive-outline" onClick={() => save(true)} disabled={update.isPending || cards.length <= 1}>
          Xóa thẻ
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Hủy
        </Button>
        <Button onClick={() => save()} loading={update.isPending} loadingText="Đang lưu…" disabled={!front.trim() || !back.trim()}>
          Lưu và duyệt
        </Button>
      </div>
    </div>
  );
}
