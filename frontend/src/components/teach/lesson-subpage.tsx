"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Skeleton } from "@/components/ui/misc";
import { useCourse, useLesson } from "@/lib/queries";
import { LessonTabs } from "./lesson-tabs";

/** Khung chung cho trang Câu hỏi / Quiz của một bài trong trình soạn. */
export function LessonSubpage({ slug, lessonId, children }: { slug: string; lessonId: string; children: React.ReactNode }) {
  const course = useCourse(slug);
  const lesson = useLesson(lessonId);
  return (
    <div className="mx-auto max-w-4xl">
      <Link href={`/teach/${slug}`} className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {course.data?.title ?? "Khóa học"}
      </Link>
      {lesson.data ? (
        <h1 className="mb-4 text-2xl font-semibold md:text-3xl">{lesson.data.title}</h1>
      ) : (
        <Skeleton className="mb-4 h-9 w-2/3" />
      )}
      <LessonTabs slug={slug} lessonId={lessonId} />
      {children}
    </div>
  );
}
