"use client";

import { useParams } from "next/navigation";
import { LessonSubpage } from "@/components/teach/lesson-subpage";
import { QuizManager } from "@/components/teach/quiz-manager";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function LessonQuizzesPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth staff>
      <LessonSubpage slug={slug} lessonId={lessonId}>
        <QuizManager key={lessonId} lessonId={lessonId} />
      </LessonSubpage>
    </RequireAuth>
  );
}
