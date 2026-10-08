"use client";

import { Tabs } from "radix-ui";
import { cn } from "@/lib/utils";

export type StudyTab = "tutor" | "studio" | "documents" | "notes";

const TABS: { value: StudyTab; label: string }[] = [
  { value: "tutor", label: "AI Tutor" },
  { value: "studio", label: "Studio" },
  { value: "documents", label: "Tài liệu" },
  { value: "notes", label: "Ghi chú" },
];

/** Các tab của cột trợ lý học tập (desktop) / khung trượt (điện thoại). Radix Tabs: ← → chuyển tab bằng bàn phím. */
export function StudyTabs({
  value,
  onChange,
  panels,
}: {
  value: StudyTab;
  onChange: (v: StudyTab) => void;
  panels: Record<StudyTab, React.ReactNode>;
}) {
  return (
    <Tabs.Root value={value} onValueChange={(v) => onChange(v as StudyTab)} className="flex h-full flex-col">
      <Tabs.List aria-label="Trợ lý học tập" className="flex shrink-0 border-b px-2">
        {TABS.map((t) => (
          <Tabs.Trigger
            key={t.value}
            value={t.value}
            className={cn(
              "h-11 flex-1 border-b-2 border-transparent px-2 text-sm text-muted-foreground transition-colors hover:text-foreground",
              "data-[state=active]:border-primary data-[state=active]:font-medium data-[state=active]:text-foreground",
            )}
          >
            {t.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {TABS.map((t) => (
        // forceMount + hidden: đổi tab không làm mất hội thoại / trạng thái đang soạn của tab khác
        <Tabs.Content key={t.value} value={t.value} forceMount hidden={value !== t.value} className="min-h-0 flex-1">
          {panels[t.value]}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}
