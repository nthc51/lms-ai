"use client";

import { cn } from "@/lib/utils";

/** Nhóm nút lọc (một nút được chọn). Dùng aria-pressed để trình đọc màn hình biết nút nào đang bật. */
export function FilterTabs<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-9 rounded-full border px-4 text-sm transition-colors",
            value === o.value ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
