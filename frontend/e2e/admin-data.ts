/** Dữ liệu giả cho khu quản trị (E2E). */
export const admin = { id: "u-9", email: "admin@example.com", full_name: "Quản trị viên", role: "admin", teacher_status: null };

export const pendingTeacher = {
  id: "u-3",
  email: "cuong@gv.vn",
  full_name: "Phạm Văn Cường",
  role: "teacher",
  teacher_status: "pending",
  locked_at: null,
  review_note: null,
  created_at: "2026-10-05T02:00:00Z",
  course_count: 0,
  enrollment_count: 0,
};

export const studentRow = {
  ...pendingTeacher,
  id: "u-1",
  email: "an@sv.vn",
  full_name: "Nguyễn Văn An",
  role: "student",
  teacher_status: null,
  enrollment_count: 2,
};

export const stats = (over: Record<string, unknown> = {}) => ({
  students: 120,
  teachers: 8,
  pending_teachers: 1,
  locked_users: 0,
  courses_published: 12,
  courses_draft: 3,
  courses_hidden: 0,
  enrollments: 340,
  tutor_questions_7d: 85,
  quiz_submissions_7d: 41,
  failed_jobs_7d: 2,
  tutor_downvotes_7d: 3,
  signups_14d: Array.from({ length: 14 }, (_, i) => ({ day: new Date(Date.UTC(2026, 8, 23 + i)).toISOString().slice(0, 10), count: i % 4 })),
  ...over,
});

export const adminCourse = (over: Record<string, unknown> = {}) => ({
  id: "11111111-1111-1111-1111-111111111111",
  title: "Giải tích 1",
  slug: "giai-tich-1",
  status: "published",
  teacher_id: "u-2",
  teacher_name: "Trần Thị Bình",
  teacher_email: "gv@lms.vn",
  created_at: "2026-09-01T00:00:00Z",
  lesson_count: 2,
  enrollment_count: 35,
  hidden_at: null,
  hidden_reason: null,
  ...over,
});

export const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, size: 20 });
