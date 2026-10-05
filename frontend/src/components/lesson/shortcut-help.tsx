"use client";

import { Dialog, DialogContent } from "@/components/ui/dialog";

const SHORTCUTS = [
  ["/", "Mở AI Tutor"],
  ["F", "Bật/tắt chế độ tập trung"],
  ["←  →", "Bài trước / bài sau"],
  ["Esc", "Đóng panel"],
  ["?", "Xem bảng phím tắt này"],
];

export function ShortcutHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Phím tắt">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="contents">
              <dt>
                <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
              </dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
