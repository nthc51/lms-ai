"use client";

import { useParams } from "next/navigation";
import { QuizPlayer } from "@/components/quiz/quiz-player";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function QuizPage() {
  const { slug, lessonId, quizId } = useParams<{ slug: string; lessonId: string; quizId: string }>();
  return (
    <RequireAuth>
      <QuizPlayer key={quizId} slug={slug} lessonId={lessonId} quizId={quizId} />
    </RequireAuth>
  );
}
