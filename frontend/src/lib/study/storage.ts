// Tiện ích lưu trên trình duyệt cho buổi học dài (design-system §8).
// Mọi truy cập localStorage đều bọc try/catch: chế độ ẩn danh có thể ném lỗi.

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // bỏ qua: chỉ là tiện ích
  }
}

export const READER_MIN = 15;
export const READER_MAX = 21;
export const READER_DEFAULT = 17;

export const readerSize = {
  get: () => Math.min(READER_MAX, Math.max(READER_MIN, read("lms:reader-size", READER_DEFAULT))),
  set: (px: number) => write("lms:reader-size", Math.min(READER_MAX, Math.max(READER_MIN, px))),
};

/** Bài học gần nhất của mỗi khóa → nút "Học tiếp". */
export const lastLesson = {
  get: (courseId: string) => read<string | null>(`lms:last-lesson:${courseId}`, null),
  set: (courseId: string, lessonId: string) => write(`lms:last-lesson:${courseId}`, lessonId),
};

/** Vị trí cuộn trong bài (tỉ lệ 0–1, không phụ thuộc cỡ chữ). */
export const scrollPosition = {
  get: (lessonId: string) => read<number>(`lms:scroll:${lessonId}`, 0),
  set: (lessonId: string, ratio: number) => write(`lms:scroll:${lessonId}`, Math.round(ratio * 1000) / 1000),
};

export type BreakPrefs = { enabled: boolean; snoozeUntil: number };
export const breakPrefs = {
  get: () => read<BreakPrefs>("lms:break", { enabled: true, snoozeUntil: 0 }),
  set: (p: BreakPrefs) => write("lms:break", p),
};
