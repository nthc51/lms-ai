// Bài làm gần nhất của mỗi quiz trên máy này. Backend chưa có API "danh sách bài làm của tôi"
// (để tầng B1), nên đây là cách để học viên quay lại xem kết quả đã nộp.

export type LastAttempt = { attemptId: string; status: "in_progress" | "completed" | "timed_out"; score?: number; passed?: boolean };

const key = (quizId: string) => `lms:quiz-attempt:${quizId}`;

export const lastAttempt = {
  get(quizId: string): LastAttempt | null {
    try {
      const raw = localStorage.getItem(key(quizId));
      return raw ? (JSON.parse(raw) as LastAttempt) : null;
    } catch {
      return null;
    }
  },
  set(quizId: string, value: LastAttempt) {
    try {
      localStorage.setItem(key(quizId), JSON.stringify(value));
    } catch {
      // chỉ là tiện ích
    }
  },
};
