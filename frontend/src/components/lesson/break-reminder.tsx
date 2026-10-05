"use client";

import { Eye } from "lucide-react";
import { Dialog as D } from "radix-ui";
import { Button } from "@/components/ui/button";
import { useBreakReminder } from "@/lib/study/use-break-reminder";

/** Hộp nhắc nghỉ mắt 20 giây sau 45 phút học (design-system §8). */
export function BreakReminder({ paused = false }: { paused?: boolean }) {
  const r = useBreakReminder({ paused });
  return (
    <D.Root open={r.due} onOpenChange={(o) => !o && r.done()}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <D.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-surface p-6 text-center shadow-lg">
          <Eye className="mx-auto size-8 text-primary" aria-hidden />
          <D.Title className="mt-3 text-lg font-semibold">Nghỉ mắt một chút nhé</D.Title>
          <D.Description className="mt-2 text-muted-foreground">
            Bạn đã học 45 phút. Hãy nhìn ra xa khoảng 6 mét trong 20 giây để mắt được nghỉ.
          </D.Description>
          <div className="mt-6 flex flex-col gap-2">
            <Button onClick={r.done}>Đã nghỉ</Button>
            <Button variant="outline" onClick={r.snooze}>
              Nhắc sau 15 phút
            </Button>
            <Button variant="link" className="mx-auto" onClick={r.disable}>
              Tắt nhắc
            </Button>
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
