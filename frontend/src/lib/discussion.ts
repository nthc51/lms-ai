"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Comment = components["schemas"]["CommentOut"];

const PAGE_SIZE = 10;

export const discussionKeys = {
  lesson: (lessonId: string) => ["discussion", lessonId] as const,
};

/** Thảo luận của một bài (B4): bình luận gốc mới nhất trước, mỗi trang 10 cái; "Xem thêm" tải trang kế. */
export function useLessonComments(lessonId: string) {
  return useInfiniteQuery({
    queryKey: discussionKeys.lesson(lessonId),
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/lessons/{lesson_id}/comments", {
          params: { path: { lesson_id: lessonId }, query: { page: pageParam, size: PAGE_SIZE } },
        }),
      ),
    getNextPageParam: (last) => (last.page * last.size < last.total ? last.page + 1 : undefined),
  });
}

export function usePostComment(lessonId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { body: string; parent_id?: string | null }) =>
      unwrap(api.POST("/api/v1/lessons/{lesson_id}/comments", { params: { path: { lesson_id: lessonId } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: discussionKeys.lesson(lessonId) }),
  });
}

export function useDeleteComment(lessonId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/comments/{comment_id}", { params: { path: { comment_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: discussionKeys.lesson(lessonId) }),
  });
}
