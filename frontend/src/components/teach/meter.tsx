/** Thanh ngang một màu; con số luôn in kèm nên không phụ thuộc màu (dataviz: text dùng màu chữ, không dùng màu thanh). */
export function Meter({ value, label }: { value: number; label: string }) {
  const v = Math.min(1, Math.max(0, value));
  return (
    <div className="flex items-center gap-3" title={label}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className="h-full rounded-full bg-accent" style={{ width: `${v * 100}%` }} />
      </div>
      <span className="w-24 shrink-0 text-right tabular-nums">{label}</span>
    </div>
  );
}
