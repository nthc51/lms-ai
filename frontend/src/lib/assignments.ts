"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Assignment = components["schemas"]["AssignmentOut"];
export type RubricItem = components["schemas"]["RubricItem"];
export type RubricItemIn = components["schemas"]["RubricItemIn"];
export type MySubmission = components["schemas"]["MySubmission"];
export type SubmissionStatus = components["schemas"]["SubmissionStatus"];
export type SubmissionListItem = components["schemas"]["SubmissionListItem"];
export type SubmissionDetail = components["schemas"]["SubmissionDetail"];

/** Trạng thái bài nộp theo góc nhìn giảng viên. */
export const SUBMISSION_STATUS_LABEL: Record<SubmissionStatus, string> = {
  submitted: "AI đang chấm",
  ai_graded: "Chờ xác nhận",
  ai_failed: "AI lỗi, cần chấm tay",
  graded: "Đã chấm",
};

export const assignmentKeys = {
  all: ["assignments"] as const,
  lesson: (lessonId: string) => ["assignments", "lesson", lessonId] as const,
  one: (id: string) => ["assignments", "one", id] as const,
  submissions: (id: string, status: SubmissionStatus | "all", page: number) =>
    ["assignments", "submissions", id, status, page] as const,
  submission: (id: string) => ["submission", id] as const,
};

/** Bài tập của một bài học: giảng viên thấy cả nháp (kèm số bài nộp), học viên thấy bài đã xuất bản (kèm bài nộp). */
export function useLessonAssignments(lessonId: string) {
  return useQuery({
    queryKey: assignmentKeys.lesson(lessonId),
    queryFn: () => unwrap(api.GET("/api/v1/assignments", { params: { query: { lesson_id: lessonId, size: 50 } } })),
  });
}

export function useAssignment(id: string) {
  return useQuery({
    queryKey: assignmentKeys.one(id),
    enabled: !!id,
    queryFn: () => unwrap(api.GET("/api/v1/assignments/{assignment_id}", { params: { path: { assignment_id: id } } })),
  });
}

export function useAssignmentMutations() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: assignmentKeys.all });
  const path = (id: string) => ({ params: { path: { assignment_id: id } } });
  return {
    create: useMutation({
      mutationFn: (body: components["schemas"]["AssignmentCreate"]) => unwrap(api.POST("/api/v1/assignments", { body })),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: components["schemas"]["AssignmentUpdate"] }) =>
        unwrap(api.PATCH("/api/v1/assignments/{assignment_id}", { ...path(id), body })),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/assignments/{assignment_id}", path(id))),
      onSuccess: refresh,
    }),
    publish: useMutation({
      mutationFn: (id: string) => unwrap(api.POST("/api/v1/assignments/{assignment_id}/publish", path(id))),
      onSuccess: refresh,
    }),
  };
}

/** Nộp / nộp lại bài (thay bài cũ). */
export function useSubmit(assignmentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["SubmissionIn"]) =>
      unwrap(
        api.PUT("/api/v1/assignments/{assignment_id}/submission", {
          params: { path: { assignment_id: assignmentId } },
          body,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: assignmentKeys.all }),
  });
}

export function useSubmissions(assignmentId: string, status: SubmissionStatus | "all", page: number) {
  return useQuery({
    queryKey: assignmentKeys.submissions(assignmentId, status, page),
    placeholderData: keepPreviousData,
    // bài "AI đang chấm" tự đổi trạng thái khi job xong: tải lại định kỳ trong lúc còn bài đang chấm
    refetchInterval: (q) => (q.state.data?.items.some((s) => s.status === "submitted") ? 5000 : false),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/assignments/{assignment_id}/submissions", {
          params: {
            path: { assignment_id: assignmentId },
            query: { page, size: 20, ...(status === "all" ? {} : { status }) },
          },
        }),
      ),
  });
}

export function useSubmission(id: string | null) {
  return useQuery({
    queryKey: assignmentKeys.submission(id ?? "none"),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === "submitted" ? 4000 : false),
    queryFn: () => unwrap(api.GET("/api/v1/submissions/{submission_id}", { params: { path: { submission_id: id! } } })),
  });
}

export function useGradeMutations(submissionId: string) {
  const qc = useQueryClient();
  const path = { params: { path: { submission_id: submissionId } } };
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: assignmentKeys.all });
    void qc.invalidateQueries({ queryKey: assignmentKeys.submission(submissionId) });
  };
  return {
    grade: useMutation({
      mutationFn: (body: components["schemas"]["GradeIn"]) =>
        unwrap(api.POST("/api/v1/submissions/{submission_id}/grade", { ...path, body })),
      onSuccess: (detail) => {
        qc.setQueryData(assignmentKeys.submission(submissionId), detail);
        void qc.invalidateQueries({ queryKey: assignmentKeys.all });
      },
      // học viên vừa nộp lại: tải bản mới để giảng viên xem rồi chấm lại
      onError: (err) => {
        if (err instanceof ApiError && err.code === "STALE_VERSION") refresh();
      },
    }),
    regrade: useMutation({
      mutationFn: () => unwrap(api.POST("/api/v1/submissions/{submission_id}/regrade", path)),
      onSuccess: refresh,
    }),
  };
}
