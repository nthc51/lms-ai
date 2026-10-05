"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { useAuth } from "@/lib/auth/auth-context";

export type CourseDetail = components["schemas"]["CourseDetail"];
export type LessonDetail = components["schemas"]["LessonDetail"];

export const qk = {
  catalog: (q: string, page: number) => ["catalog", q, page] as const,
  course: (slug: string) => ["course", slug] as const,
  myCourses: (page: number) => ["my-courses", page] as const,
  lesson: (id: string) => ["lesson", id] as const,
  lessonVideo: (id: string) => ["lesson-video", id] as const,
  teacherCourses: (page: number) => ["teacher-courses", page] as const,
  sources: (lessonId: string) => ["sources", lessonId] as const,
  job: (id: string) => ["job", id] as const,
};

export function useCatalog(q: string, page: number) {
  return useQuery({
    queryKey: qk.catalog(q, page),
    queryFn: () =>
      unwrap(api.GET("/api/v1/courses", { params: { query: { q: q || undefined, page, size: 12 } } })),
    placeholderData: keepPreviousData,
  });
}

export function useCourse(slug: string) {
  // Chờ khôi phục phiên xong mới tải: nếu không, is_enrolled/is_owner sẽ tính cho khách.
  const { status } = useAuth();
  return useQuery({
    queryKey: qk.course(slug),
    queryFn: () => unwrap(api.GET("/api/v1/courses/{slug}", { params: { path: { slug } } })),
    enabled: status !== "loading",
  });
}

export function useMyCourses(page = 1, enabled = true) {
  return useQuery({
    queryKey: qk.myCourses(page),
    queryFn: () => unwrap(api.GET("/api/v1/me/courses", { params: { query: { page, size: 20 } } })),
    enabled,
  });
}

export function useLesson(id: string) {
  return useQuery({
    queryKey: qk.lesson(id),
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: id } } })),
  });
}

/** URL video đã ký (hết hạn sau 1 giờ). 404 = bài không có video → trả null. */
export function useLessonVideo(id: string) {
  return useQuery({
    queryKey: qk.lessonVideo(id),
    queryFn: async () => {
      try {
        const { url } = await unwrap(api.GET("/api/v1/lessons/{lesson_id}/video", { params: { path: { lesson_id: id } } }));
        return url;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    staleTime: 50 * 60_000,
  });
}

export function useEnroll(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (courseId: string) =>
      unwrap(api.POST("/api/v1/courses/{course_id}/enroll", { params: { path: { course_id: courseId } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.course(slug) });
      qc.invalidateQueries({ queryKey: ["my-courses"] });
    },
  });
}

export function useSaveProgress(lessonId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["ProgressIn"]) =>
      unwrap(api.PUT("/api/v1/lessons/{lesson_id}/progress", { params: { path: { lesson_id: lessonId } }, body })),
    onSuccess: (progress) => {
      qc.setQueryData<LessonDetail>(qk.lesson(lessonId), (old) => (old ? { ...old, progress } : old));
      if (progress.status === "done") qc.invalidateQueries({ queryKey: ["my-courses"] });
    },
  });
}

/** Danh sách bài học theo thứ tự (chương → bài) để tính bài trước/sau. */
export function flattenLessons(course: CourseDetail) {
  return [...course.sections]
    .sort((a, b) => a.position - b.position)
    .flatMap((s) => [...s.lessons].sort((a, b) => a.position - b.position).map((l) => ({ ...l, sectionTitle: s.title })));
}
