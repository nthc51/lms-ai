"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { qk, type CourseDetail } from "@/lib/queries";

export type SourceOut = components["schemas"]["SourceOut"];

export function useTeacherCourses(page = 1) {
  return useQuery({
    queryKey: qk.teacherCourses(page),
    queryFn: () => unwrap(api.GET("/api/v1/teacher/courses", { params: { query: { page, size: 50 } } })),
  });
}

/** Danh sách khóa của giảng viên (mọi trang) cần tải lại sau khi tạo, xuất bản hoặc xóa khóa. */
const TEACHER_COURSES_KEY = qk.teacherCoursesAll;

export function useCreateCourse() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["CourseCreate"]) => unwrap(api.POST("/api/v1/courses", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEACHER_COURSES_KEY }),
  });
}

function useRefreshingMutation<A>(slug: string, fn: (a: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: qk.course(slug) }) });
}

/** Mọi thao tác sửa cấu trúc khóa: gọi API rồi tải lại chi tiết khóa (nguồn sự thật duy nhất). */
export function useCourseMutations(course: CourseDetail) {
  const qc = useQueryClient();
  const slug = course.slug;
  const refresh = () => qc.invalidateQueries({ queryKey: qk.course(slug) });
  const cid = { params: { path: { course_id: course.id } } };

  return {
    updateCourse: useRefreshingMutation(slug, (body: components["schemas"]["CourseUpdate"]) => unwrap(api.PATCH("/api/v1/courses/{course_id}", { ...cid, body }))),
    publish: useMutation({
      mutationFn: () => unwrap(api.POST("/api/v1/courses/{course_id}/publish", cid)),
      onSuccess: () => Promise.all([refresh(), qc.invalidateQueries({ queryKey: TEACHER_COURSES_KEY })]),
    }),
    deleteCourse: useMutation({
      mutationFn: () => unwrap(api.DELETE("/api/v1/courses/{course_id}", cid)),
      onSuccess: () => qc.invalidateQueries({ queryKey: TEACHER_COURSES_KEY }),
    }),
    addSection: useRefreshingMutation(slug, (title: string) => unwrap(api.POST("/api/v1/courses/{course_id}/sections", { ...cid, body: { title } }))),
    renameSection: useRefreshingMutation(slug, ({ id, title }: { id: string; title: string }) =>
      unwrap(api.PATCH("/api/v1/sections/{section_id}", { params: { path: { section_id: id } }, body: { title } })),
    ),
    deleteSection: useRefreshingMutation(slug, (id: string) => unwrap(api.DELETE("/api/v1/sections/{section_id}", { params: { path: { section_id: id } } }))),
    addLesson: useRefreshingMutation(slug, ({ sectionId, title }: { sectionId: string; title: string }) =>
      unwrap(api.POST("/api/v1/sections/{section_id}/lessons", { params: { path: { section_id: sectionId } }, body: { title, content_md: "" } })),
    ),
    deleteLesson: useRefreshingMutation(slug, (id: string) => unwrap(api.DELETE("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: id } } }))),
    /** Sắp xếp lạc quan: đổi thứ tự ngay trên màn hình, lỗi thì trả về thứ tự cũ (design-system §5.3). */
    reorder: useMutation({
      mutationFn: (sections: CourseDetail["sections"]) =>
        unwrap(
          api.PATCH("/api/v1/courses/{course_id}/reorder", {
            ...cid,
            body: { sections: sections.map((s) => ({ id: s.id, lesson_ids: s.lessons.map((l) => l.id) })) },
          }),
        ),
      onMutate: async (sections) => {
        await qc.cancelQueries({ queryKey: qk.course(course.slug) });
        const previous = qc.getQueryData<CourseDetail>(qk.course(course.slug));
        qc.setQueryData<CourseDetail>(qk.course(course.slug), (old) =>
          old
            ? {
                ...old,
                sections: sections.map((s, i) => ({ ...s, position: i, lessons: s.lessons.map((l, j) => ({ ...l, position: j })) })),
              }
            : old,
        );
        return { previous };
      },
      onError: (_e, _v, ctx) => ctx?.previous && qc.setQueryData(qk.course(course.slug), ctx.previous),
      onSettled: refresh,
    }),
  };
}

/** Sắp xếp sections/lessons theo position, trả về bản sao để chỉnh. */
export function sortedSections(course: CourseDetail) {
  return [...course.sections]
    .sort((a, b) => a.position - b.position)
    .map((s) => ({ ...s, lessons: [...s.lessons].sort((a, b) => a.position - b.position) }));
}

export function moveItem<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length || from === to) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function useLessonSources(lessonId: string) {
  return useQuery({
    queryKey: qk.sources(lessonId),
    queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/sources", { params: { path: { lesson_id: lessonId } } })),
    // còn tài liệu đang xử lý thì hỏi lại mỗi 3 giây; xong hết thì dừng
    refetchInterval: (q) => (q.state.data?.some((s) => s.status === "pending" || s.status === "processing") ? 3000 : false),
  });
}

export function useSourceActions(lessonId: string) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: qk.sources(lessonId) });
  return {
    attach: useMutation({
      mutationFn: (assetId: string) =>
        unwrap(api.POST("/api/v1/lessons/{lesson_id}/sources", { params: { path: { lesson_id: lessonId } }, body: { asset_id: assetId } })),
      onSuccess: refresh,
    }),
    reprocess: useMutation({
      mutationFn: (sourceId: string) =>
        unwrap(api.POST("/api/v1/sources/{source_id}/reprocess", { params: { path: { source_id: sourceId } } })),
      onSuccess: refresh,
    }),
  };
}

export function useSourcePages(sourceId: string | null, page: number) {
  return useQuery({
    queryKey: ["source-pages", sourceId, page],
    enabled: !!sourceId,
    queryFn: () =>
      unwrap(api.GET("/api/v1/sources/{source_id}/pages", { params: { path: { source_id: sourceId! }, query: { page, size: 10 } } })),
  });
}
