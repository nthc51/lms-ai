import type * as React from "react";

type Cleanup = (() => void) | void;

/**
 * Ref callback cho <video>: gán videoRef và gọi `bind`. Vì trả về cleanup nên React 19 không gọi lại
 * ref với null khi unmount — cleanup phải tự xoá videoRef để bài kế không đọc currentTime của video cũ.
 */
export function attachVideoRef(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  bind: (el: HTMLVideoElement | null) => Cleanup,
  el: HTMLVideoElement | null,
): () => void {
  videoRef.current = el;
  const cleanup = bind(el);
  return () => {
    if (cleanup) cleanup();
    if (videoRef.current === el) videoRef.current = null;
  };
}
