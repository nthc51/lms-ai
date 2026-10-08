"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type AdminStats = components["schemas"]["AdminStats"];
export type AdminUser = components["schemas"]["AdminUserOut"];
export type AdminCourse = components["schemas"]["AdminCourseOut"];
export type AdminAction = components["schemas"]["AdminActionOut"];
export type TutorFeedback = components["schemas"]["TutorFeedbackItem"];

export type UserFilter = {
  role?: "student" | "teacher" | "admin";
  status?: "pending" | "approved" | "rejected" | "locked" | "unverified";
  q?: string;
  page: number;
};
export type CourseFilter = { status?: "published" | "draft" | "hidden"; q?: string; page: number };

/** Mọi khóa của khu quản trị bắt đầu bằng "admin": một thao tác xong thì làm mới cả khu (số liệu, danh sách, nhật ký). */
const ADMIN = ["admin"] as const;
export const adminKeys = {
  all: ADMIN,
  stats: [...ADMIN, "stats"] as const,
  users: (f: UserFilter) => [...ADMIN, "users", f] as const,
  courses: (f: CourseFilter) => [...ADMIN, "courses", f] as const,
  actions: (page: number) => [...ADMIN, "actions", page] as const,
  feedback: (page: number) => [...ADMIN, "feedback", page] as const,
};

export const PAGE_SIZE = 20;

export function useAdminStats() {
  return useQuery({ queryKey: adminKeys.stats, queryFn: () => unwrap(api.GET("/api/v1/admin/stats")) });
}

export function useAdminUsers(f: UserFilter) {
  return useQuery({
    queryKey: adminKeys.users(f),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/users", {
          params: { query: { role: f.role, status: f.status, q: f.q || undefined, page: f.page, size: PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useAdminCourses(f: CourseFilter) {
  return useQuery({
    queryKey: adminKeys.courses(f),
    queryFn: () =>
      unwrap(api.GET("/api/v1/admin/courses", { params: { query: { status: f.status, q: f.q || undefined, page: f.page, size: PAGE_SIZE } } })),
    placeholderData: keepPreviousData,
  });
}

export function useAdminActions(page: number, size = PAGE_SIZE) {
  return useQuery({
    queryKey: [...adminKeys.actions(page), size],
    queryFn: () => unwrap(api.GET("/api/v1/admin/actions", { params: { query: { page, size } } })),
    placeholderData: keepPreviousData,
  });
}

export function useAdminTutorFeedback(page: number, size = PAGE_SIZE) {
  return useQuery({
    queryKey: [...adminKeys.feedback(page), size],
    queryFn: () => unwrap(api.GET("/api/v1/admin/tutor-feedback", { params: { query: { page, size } } })),
    placeholderData: keepPreviousData,
  });
}

/** Tải CSV theo đúng bộ lọc đang xem (qua API client để có token và tự refresh). */
export async function downloadUsersCsv(f: Omit<UserFilter, "page">) {
  const blob = await unwrap(
    api.GET("/api/v1/admin/users/export", { params: { query: { role: f.role, status: f.status, q: f.q || undefined } }, parseAs: "blob" }),
  );
  const url = URL.createObjectURL(blob as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nguoi-dung-${isoDateVN(new Date())}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Thu hồi ngay sau click làm hỏng tải xuống trên Safari / Firefox cũ: đợi một nhịp.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function useAdminMutation<A>(fn: (a: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    // Ẩn / hiện khóa cũng đổi danh mục công khai và trang chi tiết khóa đang cache.
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ADMIN }),
        qc.invalidateQueries({ queryKey: ["catalog"] }),
        qc.invalidateQueries({ queryKey: ["course"] }),
      ]),
  });
}

const uid = (id: string) => ({ params: { path: { user_id: id } } });
const cid = (id: string) => ({ params: { path: { course_id: id } } });

export function useAdminActionsMutations() {
  return {
    approve: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/teachers/{user_id}/approve", uid(id)))),
    reject: useAdminMutation(({ id, reason }: { id: string; reason: string }) =>
      unwrap(api.POST("/api/v1/admin/teachers/{user_id}/reject", { ...uid(id), body: { reason } })),
    ),
    lock: useAdminMutation(({ id, reason }: { id: string; reason?: string }) =>
      unwrap(api.POST("/api/v1/admin/users/{user_id}/lock", { ...uid(id), body: { reason: reason || null } })),
    ),
    unlock: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/users/{user_id}/unlock", uid(id)))),
    hide: useAdminMutation(({ id, reason }: { id: string; reason: string }) =>
      unwrap(api.POST("/api/v1/admin/courses/{course_id}/hide", { ...cid(id), body: { reason } })),
    ),
    unhide: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/courses/{course_id}/unhide", cid(id)))),
  };
}

const ACTION_LABEL: Record<string, string> = {
  approve_teacher: "Duyệt giảng viên",
  reject_teacher: "Từ chối giảng viên",
  lock_user: "Khóa tài khoản",
  unlock_user: "Mở khóa tài khoản",
  hide_course: "Ẩn khóa học",
  unhide_course: "Hiện lại khóa học",
};
export const actionLabel = (a: string) => ACTION_LABEL[a] ?? a;

const dateFmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Ho_Chi_Minh" });
const timeFmt = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
export const fmtDate = (iso: string) => dateFmt.format(new Date(iso));
/** yyyy-mm-dd theo giờ Việt Nam (toISOString là giờ UTC: 0h–7h sáng sẽ ra ngày hôm trước). */
export const isoDateVN = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(d);
export const fmtDateTime = (iso: string) => timeFmt.format(new Date(iso));
