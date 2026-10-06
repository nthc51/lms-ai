import { L1 } from "./mock-api";

export const QUIZ_ID = "44444444-4444-4444-4444-444444444444";
export const ATTEMPT_ID = "55555555-5555-5555-5555-555555555555";

const opts = (a: string, b: string, c: string, d: string) => [
  { id: "A", text: a },
  { id: "B", text: b },
  { id: "C", text: c },
  { id: "D", text: d },
];

export const quizQuestions = [
  { id: "q-1", stem: "Đạo hàm của hàm hằng bằng bao nhiêu?", options: opts("0", "1", "Chính hằng số đó", "Không xác định"), correct: "A" },
  { id: "q-2", stem: "Đạo hàm của x² là gì?", options: opts("x", "2x", "x²", "2"), correct: "B" },
  { id: "q-3", stem: "Đạo hàm là giới hạn của tỉ số nào?", options: opts("Δy/Δx", "Δx/Δy", "y/x", "x·y"), correct: "A" },
];

export const quiz = (over: Record<string, unknown> = {}) => ({
  id: QUIZ_ID,
  lesson_id: L1,
  title: "Kiểm tra đạo hàm cơ bản",
  max_attempts: 2,
  pass_score: 60,
  status: "published",
  question_count: quizQuestions.length,
  created_at: "2026-10-01T00:00:00Z",
  attempts_used: 0,
  questions: null,
  ...over,
});

export const attempt = (answers: Record<string, string> = {}) => ({
  id: ATTEMPT_ID,
  quiz_id: QUIZ_ID,
  attempt_no: 1,
  status: "in_progress",
  started_at: "2026-10-06T00:00:00Z",
  deadline_at: null,
  questions: quizQuestions.map(({ id, stem, options }) => ({ id, stem, options })),
  answers,
});

export function result(answers: Record<string, string>) {
  const questions = quizQuestions.map((q) => ({
    id: q.id,
    stem: q.stem,
    options: q.options,
    selected_option_id: answers[q.id] ?? null,
    correct_option_id: q.correct,
    is_correct: answers[q.id] === q.correct,
    explanation: `Giải thích cho câu "${q.stem}"`,
  }));
  const correct = questions.filter((q) => q.is_correct).length;
  const score = Math.round((correct / questions.length) * 10000) / 100;
  return {
    attempt_id: ATTEMPT_ID,
    quiz_id: QUIZ_ID,
    attempt_no: 1,
    status: "completed",
    score,
    passed: score >= 60,
    correct_count: correct,
    total: questions.length,
    submitted_at: "2026-10-06T00:05:00Z",
    questions,
  };
}

export const bankQuestion = (id: string, review_status: string, over: Record<string, unknown> = {}) => ({
  id,
  lesson_id: L1,
  stem: `Câu hỏi ${id}: đạo hàm của sin x là gì?`,
  options: opts("cos x", "-cos x", "sin x", "-sin x"),
  correct_option_id: "A",
  explanation: "Theo bảng đạo hàm cơ bản.",
  difficulty: "medium",
  origin: "ai",
  review_status,
  self_check_flag: false,
  ai_original: null,
  prompt_version: "quiz_generate@v1",
  source_chunk_id: null,
  source_page_no: 3,
  source_excerpt: "(sin x)' = cos x với mọi x thực.",
  created_at: "2026-10-06T00:00:00Z",
  ...over,
});
