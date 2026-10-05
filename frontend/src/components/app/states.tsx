import { AlertTriangle, type LucideIcon } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";

/** Trạng thái trống: icon + 1 câu + 1 hành động gợi ý (design-system §6). */
export function EmptyState({
  icon: Icon,
  title,
  action,
}: {
  icon: LucideIcon;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center">
      <Icon className="size-8 text-muted-foreground" aria-hidden />
      <p className="text-muted-foreground">{title}</p>
      {action}
    </div>
  );
}

/** Lỗi: câu dễ hiểu + Thử lại + request_id nhỏ để báo lỗi. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border border-destructive/40 p-8 text-center">
      <AlertTriangle className="size-7 text-destructive" aria-hidden />
      <p>{errorMessage(error)}</p>
      {onRetry ? (
        <Button variant="outline" onClick={onRetry}>
          Thử lại
        </Button>
      ) : null}
      {requestId ? <p className="text-xs text-muted-foreground">Mã lỗi: {requestId}</p> : null}
    </div>
  );
}

export function CardListSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label="Đang tải">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="space-y-3 rounded-lg border p-4">
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      ))}
    </div>
  );
}

/** Tiêu đề trang: 24px điện thoại, 30px desktop, đậm 600. */
export function PageHeader({ title, actions, children }: { title: string; actions?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 md:mb-8">
      <div>
        <h1 className="text-2xl font-semibold md:text-3xl">{title}</h1>
        {children ? <div className="mt-1 text-muted-foreground">{children}</div> : null}
      </div>
      {actions}
    </div>
  );
}
