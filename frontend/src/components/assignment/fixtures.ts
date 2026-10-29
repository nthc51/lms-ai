// Dữ liệu mẫu dùng chung cho test bài tập (B5)
export const assignment = (over: Record<string, unknown> = {}) => ({
  id: "as-1",
  lesson_id: "l1",
  lesson_title: "Tìm kiếm",
  course_slug: "khoa",
  title: "Bài tập tìm kiếm nhị phân",
  instructions: "Giải thích **tìm kiếm nhị phân**.",
  due_at: null,
  rubric: [
    { key: "c1", criterion: "Đúng khái niệm", max_points: 6, description: "Nêu đúng điều kiện" },
    { key: "c2", criterion: "Trình bày", max_points: 4, description: "" },
  ],
  max_total: 10,
  status: "published",
  created_at: "2026-10-29T00:00:00Z",
  submission_count: null,
  to_review: null,
  my_submission: null,
  ...over,
});

export const mySubmission = (over: Record<string, unknown> = {}) => ({
  id: "sub-1",
  version: 1,
  status: "submitted",
  submitted_at: "2026-10-29T01:00:00Z",
  text_content: "Bài làm của em",
  file: null,
  final_scores: null,
  final_total: null,
  teacher_feedback: null,
  graded_at: null,
  ...over,
});
