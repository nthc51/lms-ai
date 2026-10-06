"use client";

import { useParams } from "next/navigation";
import { LessonSubpage } from "@/components/teach/lesson-subpage";
import { QuestionBank } from "@/components/teach/question-bank";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function LessonQuestionsPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth staff>
      <LessonSubpage slug={slug} lessonId={lessonId}>
        <QuestionBank key={lessonId} lessonId={lessonId} />
      </LessonSubpage>
    </RequireAuth>
  );
}
