"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { ErrorState, PageHeader } from "@/components/app/states";
import { ActionLog } from "@/components/admin/action-log";
import { AiUsageTable, SignupChart, StatTiles } from "@/components/admin/overview";
import { UserTable } from "@/components/admin/user-table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { useAdminActions, useAdminStats, useAdminUsers } from "@/lib/admin-queries";

export default function AdminHome() {
  const stats = useAdminStats();
  const pending = useAdminUsers({ role: "teacher", status: "pending", page: 1 });
  const actions = useAdminActions(1, 8);

  return (
    <>
      <PageHeader title="Tổng quan hệ thống">Tình hình người dùng, khóa học và các việc cần xử lý.</PageHeader>
      {stats.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : stats.isError ? (
        <ErrorState error={stats.error} onRetry={() => stats.refetch()} />
      ) : (
        <div className="space-y-6">
          <StatTiles s={stats.data} />
          <SignupChart days={stats.data.signups_14d} />
          <section aria-labelledby="ai-usage-title">
            <h2 id="ai-usage-title" className="mb-3 text-lg font-semibold">
              Token AI 7 ngày
            </h2>
            <AiUsageTable rows={stats.data.ai_usage_7d} />
          </section>
        </div>
      )}

      <section className="mt-10" aria-labelledby="pending-title">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id="pending-title" className="text-lg font-semibold">
            Giảng viên chờ duyệt
          </h2>
          <Button asChild variant="link">
            <Link href="/admin/users?tab=pending">
              Xem tất cả <ArrowRight />
            </Link>
          </Button>
        </div>
        {pending.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : pending.isError ? (
          <ErrorState error={pending.error} onRetry={() => pending.refetch()} />
        ) : pending.data.items.length === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-muted-foreground">Không có giảng viên nào đang chờ duyệt.</p>
        ) : (
          <UserTable users={pending.data.items.slice(0, 5)} caption="Giảng viên chờ duyệt" />
        )}
      </section>

      <section className="mt-10" aria-labelledby="log-title">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id="log-title" className="text-lg font-semibold">
            Hoạt động quản trị gần đây
          </h2>
          <Button asChild variant="link">
            <Link href="/admin/activity">
              Nhật ký đầy đủ <ArrowRight />
            </Link>
          </Button>
        </div>
        {actions.isPending ? <Skeleton className="h-24 w-full" /> : actions.isError ? <ErrorState error={actions.error} onRetry={() => actions.refetch()} /> : <ActionLog items={actions.data.items} />}
      </section>
    </>
  );
}
