"use client";

import { useParams } from "next/navigation";
import { AssignmentManager } from "@/components/teach/assignment-manager";
import { LessonSubpage } from "@/components/teach/lesson-subpage";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function LessonAssignmentsPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth staff>
      <LessonSubpage slug={slug} lessonId={lessonId}>
        <AssignmentManager key={lessonId} slug={slug} lessonId={lessonId} />
      </LessonSubpage>
    </RequireAuth>
  );
}
