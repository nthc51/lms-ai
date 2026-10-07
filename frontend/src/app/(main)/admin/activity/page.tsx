"use client";

import * as React from "react";
import { ErrorState, PageHeader } from "@/components/app/states";
import { ActionLog } from "@/components/admin/action-log";
import { Pagination } from "@/components/course/course-card";
import { Skeleton } from "@/components/ui/misc";
import { useAdminActions } from "@/lib/admin-queries";

export default function AdminActivityPage() {
  const [page, setPage] = React.useState(1);
  const actions = useAdminActions(page);
  return (
    <>
      <PageHeader title="Nhật ký quản trị">Mọi thao tác duyệt, từ chối, khóa tài khoản và ẩn khóa học.</PageHeader>
      {actions.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : actions.isError ? (
        <ErrorState error={actions.error} onRetry={() => actions.refetch()} />
      ) : (
        <>
          <ActionLog items={actions.data.items} />
          <Pagination page={page} total={actions.data.total} size={actions.data.size} onPage={setPage} />
        </>
      )}
    </>
  );
}
