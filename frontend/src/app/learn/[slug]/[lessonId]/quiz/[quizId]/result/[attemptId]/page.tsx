"use client";

import { useParams } from "next/navigation";
import { QuizResult } from "@/components/quiz/quiz-result";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function QuizResultPage() {
  const { slug, lessonId, quizId, attemptId } = useParams<{ slug: string; lessonId: string; quizId: string; attemptId: string }>();
  return (
    <RequireAuth>
      <QuizResult slug={slug} lessonId={lessonId} quizId={quizId} attemptId={attemptId} />
    </RequireAuth>
  );
}
