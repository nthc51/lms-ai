/**
 * Đổi các dấu [n] trong câu trả lời thành link markdown [n](#cite-n) để render thành chip.
 * Chỉ đổi khi n có trong danh sách nguồn; bỏ qua phần trong code (`...` và ```...```).
 */
export function linkCitations(text: string, validNumbers: Set<number>): string {
  const parts = text.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  return parts
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(/\[(\d{1,2})\](?!\()/g, (m, n) => (validNumbers.has(Number(n)) ? `[${n}](#cite-${n})` : m)),
    )
    .join("");
}

export function formatTimestamp(sec: number) {
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}
