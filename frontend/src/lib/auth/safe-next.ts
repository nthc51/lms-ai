/** Chỉ cho phép chuyển hướng nội bộ (chặn open redirect kiểu ?next=https://evil.com hoặc //evil.com). */
export function safeNext(next: string | null | undefined, fallback = "/") {
  // URL parser bỏ \t \r \n nên "/\t/evil.com" trở thành "//evil.com"
  if (!next || /[\t\r\n]/.test(next) || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}
