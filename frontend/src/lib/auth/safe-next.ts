/** Chỉ cho phép chuyển hướng nội bộ (chặn open redirect kiểu ?next=https://evil.com hoặc //evil.com). */
export function safeNext(next: string | null | undefined, fallback = "/") {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}
