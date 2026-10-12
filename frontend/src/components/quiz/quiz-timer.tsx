"use client";

import { Timer } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Số mili giây còn lại tới hạn nộp, theo đồng hồ của server (bù chênh lệch giờ máy bằng server_now lúc mở bài).
 * null = quiz không giới hạn thời gian.
 */
export function useRemainingMs(deadlineAt: string | null | undefined, serverNow: string | undefined) {
  const [serverTime, setServerTime] = React.useState<number | null>(null);
  React.useEffect(() => {
    if (!deadlineAt || !serverNow) return;
    const offset = Date.parse(serverNow) - Date.now(); // giờ server - giờ máy, tính một lần lúc mở bài
    const tick = () => setServerTime(Date.now() + offset);
    const first = window.setTimeout(tick, 0);
    const id = window.setInterval(tick, 1000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, [deadlineAt, serverNow]);
  if (!deadlineAt || serverTime === null) return null;
  return Math.max(0, Date.parse(deadlineAt) - serverTime);
}

export function formatRemaining(ms: number) {
  const total = Math.ceil(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mmss = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return h > 0 ? `${h}:${mmss}` : mmss;
}

/** Đồng hồ đếm ngược. Trình đọc màn hình chỉ được báo ở các mốc 5 phút, 1 phút, 10 giây (không đọc mỗi giây). */
export function QuizTimer({ remainingMs }: { remainingMs: number }) {
  const minutesLeft = remainingMs / 60000;
  const milestone =
    remainingMs <= 10000 ? "Còn 10 giây" : minutesLeft <= 1 ? "Còn 1 phút" : minutesLeft <= 5 ? "Còn 5 phút" : "";
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-sm tabular-nums",
        minutesLeft <= 1 ? "border-destructive/60 text-destructive" : "text-foreground",
      )}
    >
      <Timer className="size-4" aria-hidden />
      <span role="timer" aria-label={`Thời gian còn lại ${formatRemaining(remainingMs)}`}>
        {formatRemaining(remainingMs)}
      </span>
      <span className="sr-only" aria-live="assertive">
        {milestone}
      </span>
    </div>
  );
}
