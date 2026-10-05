"use client";

import { BookOpen, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useMounted } from "@/lib/use-mounted";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Sáng", icon: Sun },
  { value: "dark", label: "Tối dịu", icon: Moon },
  { value: "sepia", label: "Giấy", icon: BookOpen },
] as const;

/** Nhóm 3 lựa chọn Sáng / Tối dịu / Giấy (design-system §5.3, phần Chung). */
export function ThemeSwitcher({ compact = false }: { compact?: boolean }) {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted(); // theme chỉ biết được trên trình duyệt
  const current = mounted ? (theme === "system" ? resolvedTheme : theme) : undefined;

  return (
    <div role="radiogroup" aria-label="Chế độ màu" className="inline-flex rounded-md border p-0.5">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={current === value}
          aria-label={compact ? label : undefined}
          title={label}
          onClick={() => setTheme(value)}
          className={cn(
            "inline-flex h-9 min-w-9 items-center justify-center gap-1.5 rounded px-2 text-sm transition-colors duration-150",
            current === value ? "bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          <Icon className="size-4" aria-hidden />
          {compact ? null : label}
        </button>
      ))}
    </div>
  );
}
