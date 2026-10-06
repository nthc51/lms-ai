"use client";

import { useParams } from "next/navigation";
import { LessonEditor } from "@/components/teach/lesson-editor";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function LessonEditorPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth staff>
      <LessonEditor slug={slug} lessonId={lessonId} />
    </RequireAuth>
  );
}
