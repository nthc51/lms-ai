"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";
import { LessonSubpage } from "@/components/teach/lesson-subpage";
import { SubmissionReview } from "@/components/teach/submission-review";
import { Skeleton } from "@/components/ui/misc";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function AssignmentSubmissionsPage() {
  const { slug, lessonId, assignmentId } = useParams<{ slug: string; lessonId: string; assignmentId: string }>();
  return (
    <RequireAuth staff>
      <LessonSubpage slug={slug} lessonId={lessonId}>
        {/* bài nộp đang chọn nằm trên URL (?bai=): useSearchParams cần Suspense */}
        <Suspense fallback={<Skeleton className="h-60 w-full" />}>
          <SubmissionReview key={assignmentId} slug={slug} lessonId={lessonId} assignmentId={assignmentId} />
        </Suspense>
      </LessonSubpage>
    </RequireAuth>
  );
}
