"use client";

import { useParams } from "next/navigation";
import { RequireAuth } from "@/lib/auth/require-auth";
import { LessonView } from "@/components/lesson/lesson-view";

export default function LearnPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth>
      <LessonView slug={slug} lessonId={lessonId} />
    </RequireAuth>
  );
}
