"use client";

import { X } from "lucide-react";
import { AlertDialog as AD, Dialog as D } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

const overlay = "fixed inset-0 z-40 bg-black/40";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <D.Portal>
      <D.Overlay className={overlay} />
      <D.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-surface p-6 shadow-lg",
          className,
        )}
      >
        <D.Title className="text-lg font-semibold">{title}</D.Title>
        {description ? <D.Description className="mt-2 text-sm text-muted-foreground">{description}</D.Description> : null}
        <div className="mt-4">{children}</div>
        <D.Close asChild>
          <Button variant="ghost" size="icon" aria-label="Đóng" className="absolute right-2 top-2">
            <X />
          </Button>
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}

/** Khung trượt: từ dưới lên trên điện thoại (85% chiều cao) — dùng cho Tutor, mục lục. */
export function Sheet({
  open,
  onOpenChange,
  title,
  side = "bottom",
  children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  side?: "bottom" | "left";
  children: React.ReactNode;
}) {
  const pos =
    side === "bottom"
      ? "inset-x-0 bottom-0 h-[85dvh] rounded-t-lg border-t"
      : "inset-y-0 left-0 w-[85vw] max-w-sm border-r";
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className={overlay} />
        <D.Content className={cn("fixed z-50 flex flex-col bg-surface shadow-lg", pos)} aria-describedby={undefined}>
          <div className="flex h-12 shrink-0 items-center justify-between border-b px-4">
            <D.Title className="font-semibold">{title}</D.Title>
            <D.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Đóng">
                <X />
              </Button>
            </D.Close>
          </div>
          <div className="min-h-0 flex-1">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

/**
 * Hộp thoại xác nhận (design-system §6): tiêu đề là câu hỏi, nút Hủy được focus sẵn,
 * nút hành động ghi động từ cụ thể. `onConfirm` trả Promise → nút hiện "đang xử lý".
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  pendingLabel,
  destructive = false,
  onConfirm,
  confirmText,
  children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  pendingLabel?: string;
  destructive?: boolean;
  onConfirm: () => Promise<unknown> | void;
  /** Nếu có: người dùng phải gõ đúng chuỗi này mới bấm được (xóa khóa học). */
  confirmText?: string;
  children?: React.ReactNode;
}) {
  const [pending, setPending] = React.useState(false);
  const [typed, setTyped] = React.useState("");
  const cancelRef = React.useRef<HTMLButtonElement>(null);
  const blocked = confirmText !== undefined && typed.trim() !== confirmText;

  async function handle(e: React.MouseEvent) {
    e.preventDefault();
    setPending(true);
    try {
      await onConfirm();
      onOpenChange(false);
      setTyped("");
    } catch {
      // lỗi đã được nơi gọi báo (toast); giữ hộp thoại mở
    } finally {
      setPending(false);
    }
  }

  return (
    <AD.Root open={open} onOpenChange={onOpenChange}>
      <AD.Portal>
        <AD.Overlay className={overlay} />
        <AD.Content
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            cancelRef.current?.focus();
          }}
          className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-surface p-6 shadow-lg"
        >
          <AD.Title className="text-lg font-semibold">{title}</AD.Title>
          <AD.Description asChild>
            <div className="mt-2 text-sm text-muted-foreground">{description}</div>
          </AD.Description>
          {children}
          {confirmText !== undefined ? (
            <label className="mt-4 block text-sm">
              Gõ <strong>{confirmText}</strong> để xác nhận
              <input
                className="mt-1.5 h-10 w-full rounded-md border bg-surface px-3"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
            </label>
          ) : null}
          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <AD.Cancel asChild>
              <Button ref={cancelRef} variant="outline" disabled={pending}>
                Hủy
              </Button>
            </AD.Cancel>
            <AD.Action asChild>
              <Button
                variant={destructive ? "destructive" : "default"}
                loading={pending}
                loadingText={pendingLabel}
                disabled={blocked}
                onClick={handle}
              >
                {confirmLabel}
              </Button>
            </AD.Action>
          </div>
        </AD.Content>
      </AD.Portal>
    </AD.Root>
  );
}
