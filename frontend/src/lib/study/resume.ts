import type { CourseDetail } from "@/lib/queries";
import { flattenLessons } from "@/lib/queries";
import { lastLesson } from "./storage";

/** Bài để "Học tiếp": bài mở gần nhất trên máy này, không có thì bài đầu tiên. */
export function resumeLessonId(course: CourseDetail): string | null {
  const lessons = flattenLessons(course);
  const last = lastLesson.get(course.id);
  if (last && lessons.some((l) => l.id === last)) return last;
  return lessons[0]?.id ?? null;
}
