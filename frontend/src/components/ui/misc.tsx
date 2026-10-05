import { Progress as ProgressPrimitive, Tooltip as TooltipPrimitive } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.ComponentProps<"span"> & { tone?: "neutral" | "primary" | "success" | "accent" | "destructive" }) {
  const tones = {
    neutral: "border-border text-muted-foreground",
    primary: "border-primary/40 text-primary",
    success: "border-success/40 text-success",
    accent: "border-accent/40 text-accent",
    destructive: "border-destructive/40 text-destructive",
  };
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium", tones[tone], className)}
      {...props}
    />
  );
}

export function Progress({ value, className, label }: { value: number; className?: string; label: string }) {
  return (
    <ProgressPrimitive.Root
      value={value}
      aria-label={label}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <ProgressPrimitive.Indicator
        className="h-full bg-accent transition-transform duration-200"
        style={{ transform: `translateX(-${100 - Math.min(100, Math.max(0, value))}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}

export const TooltipProvider = TooltipPrimitive.Provider;

/** Tooltip bắt buộc cho nút chỉ có icon (design-system §5.1). */
export function Tip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          className="z-50 rounded-md bg-foreground px-2 py-1 text-xs text-background shadow"
        >
          {label}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
