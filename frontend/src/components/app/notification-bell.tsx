"use client";

import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { Popover } from "radix-ui";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth/auth-context";
import { timeAgo } from "@/lib/format";
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  useNotificationStream,
  useUnreadCount,
} from "@/lib/notifications";
import { cn } from "@/lib/utils";

/**
 * Chuông thông báo (B6) ở thanh trên: số chưa đọc cập nhật theo thời gian thực qua SSE; bấm mở danh sách
 * 10 thông báo mới nhất. Bấm một thông báo thì đánh dấu đã đọc và mở trang liên quan.
 */
export function NotificationBell() {
  const { status } = useAuth();
  const authed = status === "authenticated";
  const [open, setOpen] = React.useState(false);
  useNotificationStream(authed);
  const unread = useUnreadCount(authed);
  const list = useNotifications(authed && open);
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  if (!authed) return null;

  const count = unread.data?.unread ?? 0;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button variant="ghost" size="icon" className="relative shrink-0" aria-label={count ? `Thông báo, ${count} chưa đọc` : "Thông báo"}>
          <Bell className="size-5" />
          {count ? (
            <span
              aria-hidden
              className="absolute right-1 top-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-primary px-1 text-[11px] font-bold leading-none text-primary-foreground"
            >
              {count > 99 ? "99+" : count}
            </span>
          ) : null}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 flex max-h-[min(70dvh,520px)] w-[min(92vw,380px)] flex-col border bg-surface shadow-md"
        >
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <h2 className="font-semibold">Thông báo</h2>
            <Button variant="ghost" size="sm" disabled={!count} loading={markAll.isPending} onClick={() => markAll.mutate()}>
              <CheckCheck /> Đã đọc hết
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {list.isPending ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : list.isError || list.data.items.length === 0 ? (
              <p className="px-4 pb-6 pt-2 text-sm text-muted-foreground">
                {list.isError ? "Chưa tải được thông báo." : "Chưa có thông báo nào."}
              </p>
            ) : (
              <ul className="flex flex-col">
                {list.data.items.map((n) => (
                  <li key={n.id}>
                    <Link
                      href={n.link}
                      onClick={() => {
                        if (!n.read) markRead.mutate(n.id);
                        setOpen(false);
                      }}
                      className={cn(
                        "flex gap-3 px-4 py-3 transition-colors duration-150 hover:bg-field-3",
                        !n.read && "bg-field-3/60",
                      )}
                    >
                      <span
                        aria-hidden
                        className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-primary")}
                      />
                      <span className="min-w-0">
                        <span className={cn("block text-sm leading-snug", !n.read && "font-semibold")}>
                          {n.read ? null : <span className="sr-only">Chưa đọc: </span>}
                          {n.title}
                        </span>
                        {n.body ? <span className="mt-0.5 line-clamp-2 block text-sm text-muted-foreground">{n.body}</span> : null}
                        <span className="mt-1 block text-xs text-muted-foreground">{timeAgo(n.created_at)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
