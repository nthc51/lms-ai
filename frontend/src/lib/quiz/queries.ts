"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import type { ReviewStatus } from "./types";

type S = components["schemas"];

export const quizKeys = {
  questions: (lessonId: string) => ["questions", lessonId] as const,
  questionList: (lessonId: string, status: ReviewStatus | "all") => ["questions", lessonId, status] as const,
  lessonQuizzes: (lessonId: string) => ["lesson-quizzes", lessonId] as const,
  quiz: (quizId: string) => ["quiz", quizId] as const,
  result: (attemptId: string) => ["attempt-result", attemptId] as const,
  analytics: (courseId: string) => ["analytics", courseId] as const,
  job: (jobId: string) => ["job", jobId] as const,
};

export function useLessonQuestions(lessonId: string, status: ReviewStatus | "all") {
  return useQuery({
    queryKey: quizKeys.questionList(lessonId, status),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/lessons/{lesson_id}/questions", {
          params: {
            path: { lesson_id: lessonId },
            query: { review_status: status === "all" ? undefined : status, size: 100 },
          },
        }),
      ),
  });
}

/** Theo dõi một job nền (vd. quiz_gen): hỏi lại mỗi 2 giây cho tới khi done/failed. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: quizKeys.job(jobId ?? "none"),
    enabled: !!jobId,
    queryFn: () => unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: jobId! } } })),
    refetchInterval: (q) => (q.state.data && ["done", "failed"].includes(q.state.data.status) ? false : 2000),
  });
}

export function useGenerateQuestions(lessonId: string) {
  return useMutation({
    mutationFn: (body: S["QuizGenerateIn"]) =>
      unwrap(api.POST("/api/v1/lessons/{lesson_id}/questions/generate", { params: { path: { lesson_id: lessonId } }, body })),
  });
}

export function useReviewQuestion(lessonId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: S["QuestionReview"] }) =>
      unwrap(api.PATCH("/api/v1/questions/{question_id}", { params: { path: { question_id: id } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: quizKeys.questions(lessonId) }),
  });
}

export function useLessonQuizzes(lessonId: string, enabled = true) {
  return useQuery({
    queryKey: quizKeys.lessonQuizzes(lessonId),
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/quizzes", { params: { query: { lesson_id: lessonId, size: 50 } } })),
  });
}

export function useQuiz(quizId: string, enabled = true) {
  return useQuery({
    queryKey: quizKeys.quiz(quizId),
    enabled: enabled && !!quizId,
    queryFn: () => unwrap(api.GET("/api/v1/quizzes/{quiz_id}", { params: { path: { quiz_id: quizId } } })),
  });
}

export function useQuizMutations(lessonId: string) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: quizKeys.lessonQuizzes(lessonId) });
  const path = (id: string) => ({ params: { path: { quiz_id: id } } });
  return {
    create: useMutation({
      mutationFn: (body: S["QuizCreate"]) => unwrap(api.POST("/api/v1/quizzes", { body })),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: S["QuizUpdate"] }) =>
        unwrap(api.PATCH("/api/v1/quizzes/{quiz_id}", { ...path(id), body })),
      onSuccess: (q) => Promise.all([refresh(), qc.invalidateQueries({ queryKey: quizKeys.quiz(q.id) })]),
    }),
    publish: useMutation({
      mutationFn: (id: string) => unwrap(api.POST("/api/v1/quizzes/{quiz_id}/publish", path(id))),
      onSuccess: (q) => Promise.all([refresh(), qc.invalidateQueries({ queryKey: quizKeys.quiz(q.id) })]),
    }),
    remove: useMutation({
      mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/quizzes/{quiz_id}", path(id))),
      onSuccess: refresh,
    }),
  };
}

export function startAttempt(quizId: string) {
  return unwrap(api.POST("/api/v1/quizzes/{quiz_id}/attempts", { params: { path: { quiz_id: quizId } } }));
}

export function saveAnswer(attemptId: string, questionId: string, optionId: string) {
  return unwrap(
    api.PUT("/api/v1/attempts/{attempt_id}/answers/{question_id}", {
      params: { path: { attempt_id: attemptId, question_id: questionId } },
      body: { selected_option_id: optionId },
    }),
  );
}

export function submitAttempt(attemptId: string, answers: Record<string, string>) {
  return unwrap(
    api.POST("/api/v1/attempts/{attempt_id}/submit", {
      params: { path: { attempt_id: attemptId } },
      // gửi kèm toàn bộ đáp án đang có: server lấy payload này thay cho bản autosave (phòng autosave lỡ nhịp)
      body: {
        final_answers: Object.entries(answers).map(([question_id, selected_option_id]) => ({ question_id, selected_option_id })),
      },
    }),
  );
}

export function useAttemptResult(attemptId: string) {
  return useQuery({
    queryKey: quizKeys.result(attemptId),
    queryFn: () => unwrap(api.GET("/api/v1/attempts/{attempt_id}/result", { params: { path: { attempt_id: attemptId } } })),
    staleTime: Infinity, // kết quả đã nộp không đổi
  });
}

/** Câu trả lời AI Tutor bị chê trong khóa (giảng viên; không có tên học viên). */
export function useCourseTutorFeedback(courseId: string | undefined) {
  return useQuery({
    queryKey: [...quizKeys.analytics(courseId ?? "none"), "tutor-feedback"],
    enabled: !!courseId,
    queryFn: () =>
      unwrap(api.GET("/api/v1/courses/{course_id}/tutor-feedback", { params: { path: { course_id: courseId! }, query: { size: 20 } } })),
  });
}

export function useCourseAnalytics(courseId: string | undefined) {
  return useQuery({
    queryKey: quizKeys.analytics(courseId ?? "none"),
    enabled: !!courseId,
    queryFn: () => unwrap(api.GET("/api/v1/courses/{course_id}/analytics", { params: { path: { course_id: courseId! } } })),
  });
}
