"use client";

import { useParams } from "next/navigation";
import { CourseEditor } from "@/components/teach/course-editor";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function CourseEditorPage() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <RequireAuth staff>
      <CourseEditor slug={slug} />
    </RequireAuth>
  );
}
