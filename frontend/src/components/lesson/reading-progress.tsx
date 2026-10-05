"use client";

import * as React from "react";
import { scrollPosition } from "@/lib/study/storage";

/**
 * Thanh 2px màu accent ở mép trên cho biết đã đọc tới đâu, đồng thời
 * nhớ vị trí cuộn của bài và khôi phục khi mở lại (design-system §7.2, §8).
 */
export function ReadingProgress({ lessonId, ready }: { lessonId: string; ready: boolean }) {
  const [pct, setPct] = React.useState(0);

  React.useEffect(() => {
    if (!ready) return;
    const ratio = scrollPosition.get(lessonId);
    const max = document.documentElement.scrollHeight - window.innerHeight;
    if (ratio > 0.02 && max > 0) window.scrollTo({ top: ratio * max });
  }, [lessonId, ready]);

  React.useEffect(() => {
    let timer: number | undefined;
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = max > 0 ? window.scrollY / max : 0;
      setPct(Math.round(ratio * 100));
      window.clearTimeout(timer);
      timer = window.setTimeout(() => scrollPosition.set(lessonId, ratio), 400);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.clearTimeout(timer);
    };
  }, [lessonId]);

  return (
    <div className="fixed inset-x-0 top-0 z-40 h-0.5" aria-hidden>
      <div className="h-full bg-accent transition-[width] duration-150" style={{ width: `${pct}%` }} />
    </div>
  );
}
