"use client";

import { PageHeader } from "@/components/app/states";
import { MyCourseList } from "@/components/course/my-course-list";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function MyCoursesPage() {
  return (
    <RequireAuth>
      <PageHeader title="Khóa của tôi" />
      <MyCourseList />
    </RequireAuth>
  );
}
