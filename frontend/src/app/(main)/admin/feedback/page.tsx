"use client";

import * as React from "react";
import { ErrorState, PageHeader } from "@/components/app/states";
import { FeedbackList } from "@/components/admin/feedback-list";
import { Pagination } from "@/components/course/course-card";
import { Skeleton } from "@/components/ui/misc";
import { useAdminTutorFeedback } from "@/lib/admin-queries";

export default function AdminFeedbackPage() {
  const [page, setPage] = React.useState(1);
  const feedback = useAdminTutorFeedback(page);
  return (
    <>
      <PageHeader title="Câu trả lời AI bị chê">
        Học viên bấm 👎 ở AI Tutor. Dùng để tìm tài liệu thiếu, câu trả lời sai hoặc AI từ chối nhầm.
      </PageHeader>
      {feedback.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : feedback.isError ? (
        <ErrorState error={feedback.error} onRetry={() => feedback.refetch()} />
      ) : (
        <>
          <FeedbackList items={feedback.data.items} showCourse />
          <Pagination page={page} total={feedback.data.total} size={feedback.data.size} onPage={setPage} />
        </>
      )}
    </>
  );
}
