"use client";

import { DropdownMenu as M } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Menu = M.Root;
export const MenuTrigger = M.Trigger;
export const MenuSeparator = () => <M.Separator className="my-1 h-px bg-border" />;

export function MenuContent({ children, align = "end" }: { children: React.ReactNode; align?: "start" | "end" }) {
  return (
    <M.Portal>
      <M.Content
        align={align}
        sideOffset={6}
        className="z-50 min-w-48 rounded-md border bg-surface p-1 shadow-md"
      >
        {children}
      </M.Content>
    </M.Portal>
  );
}

export function MenuItem({
  className,
  destructive,
  ...props
}: React.ComponentProps<typeof M.Item> & { destructive?: boolean }) {
  return (
    <M.Item
      className={cn(
        "flex min-h-10 cursor-default select-none items-center gap-2 rounded-sm px-2 text-sm outline-none data-[highlighted]:bg-muted [&_svg]:size-4",
        destructive && "text-destructive",
        className,
      )}
      {...props}
    />
  );
}
