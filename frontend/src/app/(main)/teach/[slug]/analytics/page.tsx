"use client";

import { useParams } from "next/navigation";
import { CourseAnalyticsView } from "@/components/teach/course-analytics";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function CourseAnalyticsPage() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <RequireAuth staff>
      <CourseAnalyticsView slug={slug} />
    </RequireAuth>
  );
}
