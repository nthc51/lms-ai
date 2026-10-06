# Frontend FE-2: Kế hoạch triển khai (quiz, duyệt câu hỏi, thống kê)

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Mục tiêu:** Hoàn thành phần frontend còn lại của tầng A. Học viên làm quiz ngay trong bài học: chọn đáp án có tự lưu, nộp bài có xác nhận, xem kết quả kèm giải thích. Giảng viên sinh câu hỏi bằng AI, duyệt / sửa / loại câu hỏi, tạo và xuất bản quiz, xem thống kê khóa học.

**Kiến trúc:** Dùng lại nền móng FE-1 (API client, TanStack Query, design system, E2E với API giả). Phần quiz nằm gọn trong `src/lib/quiz/*`, `src/components/quiz/*` và các component mới trong `src/components/teach/*`. **Không sửa backend**: mọi endpoint đã có từ tuần 2.

**Mã trong plan đã được chạy thử:** viết trên nhánh `main` sau khi FE-1 xong Task 17. Kết quả:

- 92 unit test pass (87 cũ, 5 mới).
- 28 test E2E pass (14 kịch bản × 2 khung hình 375/1280px, có axe WCAG AA). Trong đó có 5 kịch bản mới.
- `eslint`, `tsc`, `next build` đều sạch.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit.

---

## 0. Bối cảnh

### 0.1 Điều kiện bắt đầu

- FE-1 đã xong (Task 1–17 trên `main`), kể cả bản sửa phím tắt `use-shortcuts.ts`.
- **Không cần backend chạy** cho Task 1–11: unit test dùng MSW, E2E dùng API giả. Chỉ Task 12 cần backend thật.

### 0.2 Hợp đồng backend mà FE-2 dựa vào

Tất cả đã có trong `src/lib/api/schema.d.ts`, không cần chạy `gen:api`.

| Endpoint | Ghi chú cho frontend |
|---|---|
| `POST /lessons/{id}/questions/generate` `{count 1–30, difficulty{easy,medium,hard}}` | Trả 202 `{job_id}`. 409 khi bài chưa có tài liệu xử lý xong |
| `GET /jobs/{id}` | `status`: pending → processing → done \| failed. Lỗi nằm ở `error_msg` |
| `GET /lessons/{id}/questions?review_status=&size=100` | Mỗi câu có `review_status` (pending / approved / edited / rejected), `self_check_flag`, `source_page_no`, `source_excerpt` |
| `PATCH /questions/{id}` `{action: approve\|reject\|edit, …}` | `approve` trên câu đã loại = khôi phục. `edit` sửa xong thì thành `edited` (tính là đã duyệt). 422 khi vi phạm luật câu hỏi (đúng 4 lựa chọn khác nhau, đề ≥ 10 ký tự). 409 khi câu đang nằm trong quiz đã xuất bản |
| `GET /quizzes?lesson_id=` | Giảng viên thấy cả nháp. Học viên chỉ thấy quiz đã xuất bản, kèm `attempts_used` |
| `GET /quizzes/{id}` | Chủ khóa nhận thêm `questions` (có đáp án) |
| `POST/PATCH/DELETE /quizzes`, `POST /quizzes/{id}/publish` | Chỉ chọn được câu `approved` / `edited`. Quiz đã xuất bản thì chỉ đổi được tiêu đề. 409 nếu xóa quiz đã có bài làm |
| `POST /quizzes/{id}/attempts` | **201** là bài mới, **200** là bài đang làm dở (kèm `answers` đã lưu). 409 `QUIZ_ATTEMPT_LIMIT` khi hết lượt. Chỉ học viên gọi được |
| `PUT /attempts/{id}/answers/{qid}` `{selected_option_id}` | Tự lưu. **Gửi tuần tự** (spec). 409 `ATTEMPT_CLOSED` sau khi đã nộp |
| `POST /attempts/{id}/submit` `{final_answers?}` | `final_answers` **thay cho** bản tự lưu. Trả `AttemptResult` (có đáp án đúng và giải thích) |
| `GET /attempts/{id}/result` | 409 nếu chưa nộp |
| `GET /courses/{id}/analytics` | `enrollments`, `lessons[].completion_rate` (0..1), `quizzes[].avg_score` (%), `pass_rate` (0..1), `tutor{sessions, questions, refused_answers}` |

> **Chỗ còn thiếu ở backend (ghi cho tầng B1):** chưa có API "danh sách bài làm của tôi". FE-2 tạm lưu bài làm gần nhất của mỗi quiz vào `localStorage` (`attempt-store.ts`), đủ để học viên quay lại xem kết quả trên cùng máy. B1 nên thêm `GET /quizzes/{id}/attempts/me` để xem được trên mọi thiết bị.

### 0.3 Các quyết định thiết kế (theo design-system §5.3, §6, §8)

- **Làm quiz:**
  - Mỗi lúc hiện một câu. Đáp án là thẻ chọn cả dòng (radio gốc ẩn đi, vẫn dùng được bàn phím), cao ≥ 48px.
  - Cạnh câu có dòng "Đang lưu… / Đã lưu / Chưa lưu được".
  - Có lưới số câu để nhảy nhanh. Nút **Nộp bài** là nút chính `lg` ở câu cuối, và có thêm nút phụ ở lưới câu.
  - Hộp xác nhận ghi rõ số câu chưa trả lời, nút **Hủy** được focus sẵn.
  - Khi quiz có hạn giờ (`deadline_at`, sẽ có ở tầng B1) thì **tạm dừng nhắc nghỉ mắt**.
- **Tự lưu đáp án:** dùng hàng đợi `AnswerSaver`:
  - Gửi tuần tự, mỗi lúc một request.
  - Mỗi câu chỉ gửi lựa chọn mới nhất.
  - Lưu lỗi thì không chặn người làm bài: khi nộp, gửi lại các câu lỗi, đồng thời gửi **toàn bộ đáp án trong `final_answers`**.
- **Kết quả:**
  - Điểm hiện bằng chữ số lớn. Đạt / chưa đạt có **icon + chữ**, không chỉ dựa vào màu.
  - Mỗi câu ghi "Đúng / Sai / Chưa trả lời". Câu sai **mở sẵn phần giải thích**.
  - Có ô lọc "Chỉ xem câu sai". Nút "Làm lại" chỉ hiện khi còn lượt.
- **Duyệt câu hỏi:**
  - Duyệt là nút chính; Sửa / Loại là nút phụ.
  - **Loại có Hoàn tác trong 5 giây**: câu bị ẩn ngay, sau 5 giây mới gửi request. Nếu rời trang trong lúc chờ thì gửi luôn.
  - Câu bị AI tự kiểm tra gắn cờ có huy hiệu cảnh báo. Đoạn tài liệu nguồn và số trang nằm trong `<details>`.
- **Sinh câu hỏi:**
  - Chạy job nền, **không khóa trang**. Dòng trạng thái ghi "AI đang soạn… (≈1 phút)".
  - Job xong thì hiện toast kèm số câu chờ duyệt; job lỗi thì hiện `error_msg`.
- **Thống kê:**
  - Thẻ số lớn cho các con số chính.
  - Bảng có thanh ngang một màu (`--accent`) cho tỉ lệ, **giá trị luôn in bằng chữ** bên cạnh.
  - Bảng cuộn ngang được trên điện thoại và nhận focus bằng bàn phím (axe rule `scrollable-region-focusable`).
- **Chữ cạnh màu trạng thái:** chữ dùng màu chữ thường (`foreground`), chỉ icon mang màu success hoặc destructive. Axe đã bắt lỗi tương phản khi để chữ màu xanh lá trên nền xanh lá nhạt.
- **Bỏ toast "Đã đánh dấu học xong"** ở trang bài học. Dòng "Đã học xong bài này" đã đủ báo, còn toast ở góc dưới phải che mất nút "Bài tiếp" (E2E bắt được lỗi này).

### 0.4 File

```
frontend/src/
├── lib/quiz/
│   ├── types.ts                 # kiểu từ OpenAPI + nhãn độ khó
│   ├── answer-saver.ts (+test)  # hàng đợi tự lưu tuần tự
│   ├── queries.ts               # hook TanStack Query cho câu hỏi, quiz, bài làm, thống kê, job
│   ├── attempt-store.ts         # bài làm gần nhất của mỗi quiz (localStorage)
│   └── use-quiz-attempt.ts (+test)
├── components/quiz/
│   ├── quiz-player.tsx          # màn làm bài
│   └── quiz-result.tsx          # màn kết quả
├── components/lesson/lesson-quizzes.tsx   # danh sách quiz dưới nội dung bài
├── components/teach/
│   ├── lesson-tabs.tsx          # Nội dung | Câu hỏi | Quiz
│   ├── lesson-subpage.tsx       # khung trang con của một bài
│   ├── question-card.tsx        # một câu: xem / sửa
│   ├── question-bank.tsx        # sinh bằng AI + duyệt
│   ├── quiz-manager.tsx         # tạo / sửa / xuất bản / xóa quiz
│   └── course-analytics.tsx     # thống kê khóa
└── app/
    ├── learn/[slug]/[lessonId]/quiz/[quizId]/page.tsx
    ├── learn/[slug]/[lessonId]/quiz/[quizId]/result/[attemptId]/page.tsx
    └── (main)/teach/[slug]/{analytics, lessons/[lessonId]/questions, lessons/[lessonId]/quizzes}/page.tsx
Sửa: components/lesson/lesson-view.tsx, components/teach/lesson-editor.tsx (+test), components/teach/course-editor.tsx, e2e/mock-api.ts
E2E mới: e2e/quiz-data.ts, e2e/quiz.spec.ts, e2e/teacher-quiz.spec.ts
```

### 0.5 Quy ước

Giống FE-1 §0.5:

- Commit sau mỗi task, dạng `feat(web): …`, **không thêm trailer**.
- Lệnh chạy trong `frontend/`.
- Kiểm tra cuối mỗi task: `npm run lint && npm run typecheck && npm test`.

---

## Task 1: Kiểu dữ liệu và hàng đợi tự lưu đáp án

**Files:**
- Create: `frontend/src/lib/quiz/types.ts`, `frontend/src/lib/quiz/answer-saver.ts`
- Test: `frontend/src/lib/quiz/answer-saver.test.ts`

- [x] **Bước 1: `src/lib/quiz/types.ts`**

```ts
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type Question = S["QuestionOut"];
export type ReviewStatus = S["ReviewStatus"];
export type Difficulty = S["Difficulty"];
export type Quiz = S["QuizOut"];
export type Attempt = S["AttemptOut"];
export type AttemptResult = S["AttemptResult"];
export type CourseAnalytics = S["CourseAnalytics"];

export const DIFFICULTY_LABEL: Record<Difficulty, string> = { easy: "Dễ", medium: "Vừa", hard: "Khó" };
```

- [x] **Bước 2: Viết test (sẽ fail)** (`src/lib/quiz/answer-saver.test.ts`)

```ts
import { describe, expect, it, vi } from "vitest";
import { AnswerSaver } from "./answer-saver";

function deferred() {
  let resolve!: () => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("AnswerSaver", () => {
  it("gửi tuần tự và chỉ gửi lựa chọn mới nhất của mỗi câu", async () => {
    const calls: string[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const gates: ReturnType<typeof deferred>[] = [];
    const saver = new AnswerSaver(async (q, o) => {
      calls.push(`${q}=${o}`);
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      const g = deferred();
      gates.push(g);
      await g.promise;
      inFlight--;
    }, () => {});
    saver.enqueue("q1", "A");
    saver.enqueue("q1", "B"); // q1=A đang gửi; B chờ
    saver.enqueue("q1", "C"); // ghi đè B
    saver.enqueue("q2", "D");
    gates[0].resolve();
    await vi.waitFor(() => expect(gates.length).toBe(2));
    gates[1].resolve();
    await vi.waitFor(() => expect(gates.length).toBe(3));
    gates[2].resolve();
    await saver.flush();
    expect(calls).toEqual(["q1=A", "q1=C", "q2=D"]);
    expect(maxInFlight).toBe(1);
  });

  it("báo trạng thái saving → saved, và câu lỗi được gửi lại khi flush", async () => {
    const states: string[] = [];
    let fail = true;
    const saver = new AnswerSaver(
      async () => {
        if (fail) throw new Error("mất mạng");
      },
      (q, s) => states.push(`${q}:${s}`),
    );
    saver.enqueue("q1", "A");
    expect(await saver.flush()).toEqual(["q1"]); // đợi lần gửi đang chạy: lỗi
    expect(states).toEqual(["q1:saving", "q1:error"]);
    fail = false;
    expect(await saver.flush()).toEqual([]);
    expect(states.at(-1)).toBe("q1:saved");
  });

  it("flush trả về các câu vẫn lỗi để nơi gọi quyết định", async () => {
    const saver = new AnswerSaver(async (q) => {
      if (q === "q2") throw new Error("x");
    }, () => {});
    saver.enqueue("q1", "A");
    saver.enqueue("q2", "B");
    expect(await saver.flush()).toEqual(["q2"]);
  });
});
```

Run: `npx vitest run src/lib/quiz/answer-saver.test.ts`
Expected: FAIL với lỗi `Failed to resolve import "./answer-saver"`.

- [x] **Bước 3: Cài đặt `src/lib/quiz/answer-saver.ts`**

```ts
export type SaveState = "saving" | "saved" | "error";
export type SaveFn = (questionId: string, optionId: string) => Promise<unknown>;

/**
 * Hàng đợi tự lưu đáp án (không phụ thuộc React, dễ test).
 * - Gửi TUẦN TỰ, mỗi lúc một request (spec: autosave gửi tuần tự).
 * - Mỗi câu chỉ giữ lựa chọn mới nhất: đổi đáp án 3 lần lúc mạng chậm thì chỉ gửi bản cuối.
 * - Lỗi một câu không chặn các câu khác; câu lỗi được gửi lại ở lần `flush()` tiếp theo.
 */
export class AnswerSaver {
  private pending = new Map<string, string>();
  private failed = new Map<string, string>();
  private running: Promise<void> | null = null;

  constructor(
    private save: SaveFn,
    private onState: (questionId: string, state: SaveState) => void,
  ) {}

  enqueue(questionId: string, optionId: string) {
    this.failed.delete(questionId);
    this.pending.set(questionId, optionId);
    this.onState(questionId, "saving");
    void this.run();
  }

  /** Gửi lại các câu lỗi rồi đợi hàng đợi rỗng. Trả về các câu vẫn lỗi. */
  async flush(): Promise<string[]> {
    for (const [q, o] of this.failed) this.pending.set(q, o);
    this.failed.clear();
    await this.run();
    return [...this.failed.keys()];
  }

  private run(): Promise<void> {
    this.running ??= (async () => {
      try {
        while (this.pending.size) {
          const [questionId, optionId] = this.pending.entries().next().value as [string, string];
          this.pending.delete(questionId);
          try {
            await this.save(questionId, optionId);
            // trong lúc gửi người dùng đã chọn lại → vẫn còn "saving", vòng sau gửi bản mới
            if (!this.pending.has(questionId)) this.onState(questionId, "saved");
          } catch {
            if (!this.pending.has(questionId)) {
              this.failed.set(questionId, optionId);
              this.onState(questionId, "error");
            }
          }
        }
      } finally {
        this.running = null;
      }
    })();
    return this.running;
  }
}
```

Run: `npx vitest run src/lib/quiz/answer-saver.test.ts`
Expected: PASS (3 test). Test đầu tiên chứng minh hai điều: không bao giờ có 2 request cùng lúc (`maxInFlight === 1`), và lựa chọn bị ghi đè trong lúc chờ không bao giờ được gửi (`q1=B`).

- [x] **Bước 4: Commit**

```bash
git add frontend/src/lib/quiz && git commit -m "feat(web): sequential answer autosave queue for quizzes"
```

---

## Task 2: Truy vấn quiz và lưu bài làm gần nhất

**Files:**
- Create: `frontend/src/lib/quiz/queries.ts`, `frontend/src/lib/quiz/attempt-store.ts`

- [x] **Bước 1: `src/lib/quiz/queries.ts`**

`useJob` hỏi lại trạng thái mỗi 2 giây cho tới khi job xong. `submitAttempt` luôn gửi `final_answers`.

```ts
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
      onSuccess: refresh,
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

export function useCourseAnalytics(courseId: string | undefined) {
  return useQuery({
    queryKey: quizKeys.analytics(courseId ?? "none"),
    enabled: !!courseId,
    queryFn: () => unwrap(api.GET("/api/v1/courses/{course_id}/analytics", { params: { path: { course_id: courseId! } } })),
  });
}
```

- [x] **Bước 2: `src/lib/quiz/attempt-store.ts`**

```ts
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
```

- [x] **Bước 3: Kiểm tra và commit**

```bash
npm run typecheck
git add frontend/src/lib/quiz && git commit -m "feat(web): quiz, question and analytics queries"
```

Expected: `tsc` không lỗi. Đây là bước kiểm tra chính: nó đối chiếu mọi đường dẫn API và mọi body gửi lên với `schema.d.ts`.

---

## Task 3: Hook một lượt làm quiz

**Files:**
- Create: `frontend/src/lib/quiz/use-quiz-attempt.ts`
- Test: `frontend/src/lib/quiz/use-quiz-attempt.test.tsx`

Thiết kế:

- Đáp án hiển thị = bản server trả lúc mở bài, cộng các lựa chọn mới trong phiên. Tính bằng `useMemo`, **không `setState` trong effect** (luật `react-hooks/set-state-in-effect` của eslint-config-next 16).
- `AnswerSaver` được tạo lười theo `attempt.id`.
- Request mở bài (`POST /attempts`) chạy trong `useQuery` với `staleTime: Infinity`, `gcTime: 0`, `retry: false`. Nhờ vậy React StrictMode không gửi 2 lần, và mở lại trang thì gọi lại để nhận bài đang làm dở.

- [x] **Bước 1: Viết test (sẽ fail)** (`src/lib/quiz/use-quiz-attempt.test.tsx`)

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it } from "vitest";
import { api, server } from "@/test/msw";
import { lastAttempt } from "./attempt-store";
import { useQuizAttempt } from "./use-quiz-attempt";

const attempt = {
  id: "at-1",
  quiz_id: "qz-1",
  attempt_no: 1,
  status: "in_progress",
  started_at: "2026-10-06T00:00:00Z",
  deadline_at: null,
  questions: [
    { id: "q1", stem: "Câu 1?", options: [{ id: "A", text: "a" }, { id: "B", text: "b" }] },
    { id: "q2", stem: "Câu 2?", options: [{ id: "A", text: "a" }, { id: "B", text: "b" }] },
  ],
  answers: { q1: "B" }, // đã lưu từ lần mở trước
};

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return renderHook(() => useQuizAttempt("qz-1"), { wrapper });
}

describe("useQuizAttempt", () => {
  it("tiếp tục bài làm dở (200) với đáp án đã lưu, chọn đáp án thì tự lưu, nộp kèm final_answers", async () => {
    const saved: unknown[] = [];
    let submitted: unknown = null;
    server.use(
      http.post(api("/quizzes/qz-1/attempts"), () => HttpResponse.json(attempt, { status: 200 })),
      http.put(api("/attempts/at-1/answers/:qid"), async ({ params, request }) => {
        saved.push({ q: params.qid, ...(await request.json() as object) });
        return HttpResponse.json({ question_id: params.qid, selected_option_id: "A", answered_at: "2026-10-06T00:00:01Z" });
      }),
      http.post(api("/attempts/at-1/submit"), async ({ request }) => {
        submitted = await request.json();
        return HttpResponse.json({
          attempt_id: "at-1", quiz_id: "qz-1", attempt_no: 1, status: "completed", score: 50, passed: true,
          correct_count: 1, total: 2, submitted_at: "2026-10-06T00:01:00Z", questions: [],
        });
      }),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.answers).toEqual({ q1: "B" }));
    expect(result.current.saveStates.q1).toBe("saved");

    act(() => result.current.select("q2", "A"));
    expect(result.current.saveStates.q2).toBe("saving");
    await waitFor(() => expect(result.current.saveStates.q2).toBe("saved"));
    expect(saved).toEqual([{ q: "q2", selected_option_id: "A" }]);

    let res: Awaited<ReturnType<typeof result.current.submit>> | undefined;
    await act(async () => {
      res = await result.current.submit();
    });
    expect(res?.score).toBe(50);
    expect(submitted).toEqual({
      final_answers: [
        { question_id: "q1", selected_option_id: "B" },
        { question_id: "q2", selected_option_id: "A" },
      ],
    });
    expect(lastAttempt.get("qz-1")).toMatchObject({ attemptId: "at-1", status: "completed", score: 50 });
  });

  it("hết lượt làm bài → lỗi QUIZ_ATTEMPT_LIMIT để giao diện hiện thông báo", async () => {
    server.use(
      http.post(api("/quizzes/qz-1/attempts"), () =>
        HttpResponse.json(
          { error: { code: "QUIZ_ATTEMPT_LIMIT", message: "Bạn đã dùng hết số lần làm bài", details: {}, request_id: null } },
          { status: 409 },
        ),
      ),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.attempt.isError).toBe(true));
    expect(result.current.attempt.error).toMatchObject({ code: "QUIZ_ATTEMPT_LIMIT" });
  });
});
```

Run: `npx vitest run src/lib/quiz/use-quiz-attempt.test.tsx`
Expected: FAIL với lỗi `Failed to resolve import "./use-quiz-attempt"`.

- [x] **Bước 2: Cài đặt `src/lib/quiz/use-quiz-attempt.ts`**

```ts
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { AnswerSaver, type SaveState } from "./answer-saver";
import { lastAttempt } from "./attempt-store";
import { quizKeys, saveAnswer, startAttempt, submitAttempt } from "./queries";
import type { AttemptResult } from "./types";

/**
 * Một lượt làm quiz: mở (hoặc tiếp tục) bài làm, chọn đáp án có tự lưu tuần tự, nộp bài.
 * POST /attempts trả 201 (bài mới) hoặc 200 (đang có bài làm dở) — cả hai đều dùng tiếp được,
 * nên mở lại trang hay mở 2 tab đều quay về đúng bài đang làm với các đáp án đã lưu.
 */
export function useQuizAttempt(quizId: string) {
  const qc = useQueryClient();
  const attempt = useQuery({
    queryKey: ["attempt-open", quizId],
    queryFn: () => startAttempt(quizId),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });
  // Đáp án = bản server đã lưu (lúc mở bài) + các lựa chọn mới trong phiên này
  const [picked, setPicked] = React.useState<Record<string, string>>({});
  const [pickedStates, setPickedStates] = React.useState<Record<string, SaveState>>({});
  const saverRef = React.useRef<{ attemptId: string; saver: AnswerSaver } | null>(null);
  const a = attempt.data;
  const answers = React.useMemo(() => ({ ...(a?.answers ?? {}), ...picked }), [a, picked]);
  const saveStates = React.useMemo(
    () => ({ ...Object.fromEntries(Object.keys(a?.answers ?? {}).map((q) => [q, "saved" as SaveState])), ...pickedStates }),
    [a, pickedStates],
  );

  React.useEffect(() => {
    if (a) lastAttempt.set(quizId, { attemptId: a.id, status: "in_progress" });
  }, [a, quizId]);

  const saverFor = React.useCallback((attemptId: string) => {
    if (saverRef.current?.attemptId !== attemptId) {
      saverRef.current = {
        attemptId,
        saver: new AnswerSaver(
          (q, o) => saveAnswer(attemptId, q, o),
          (q, st) => setPickedStates((prev) => ({ ...prev, [q]: st })),
        ),
      };
    }
    return saverRef.current.saver;
  }, []);

  const select = React.useCallback(
    (questionId: string, optionId: string) => {
      if (!a) return;
      setPicked((prev) => ({ ...prev, [questionId]: optionId }));
      saverFor(a.id).enqueue(questionId, optionId);
    },
    [a, saverFor],
  );

  const submit = React.useCallback(async (): Promise<AttemptResult> => {
    if (!a) throw new Error("Bài làm chưa sẵn sàng");
    await saverFor(a.id).flush(); // đợi các lần lưu đang chạy; câu lưu lỗi vẫn được gửi trong final_answers
    const result = await submitAttempt(a.id, answers);
    lastAttempt.set(quizId, { attemptId: a.id, status: result.status, score: result.score, passed: result.passed });
    qc.setQueryData(quizKeys.result(a.id), result);
    qc.invalidateQueries({ queryKey: quizKeys.quiz(quizId) });
    qc.invalidateQueries({ queryKey: ["lesson-quizzes"] });
    return result;
  }, [a, answers, quizId, qc, saverFor]);

  return { attempt, answers, saveStates, select, submit };
}
```

Run: `npx vitest run src/lib/quiz`
Expected: PASS (5 test).

- [x] **Bước 3: Commit**

```bash
npm run lint && git add frontend/src/lib/quiz && git commit -m "feat(web): quiz attempt hook with resume, autosave and submit"
```

---

## Task 4: Màn làm quiz

**Files:**
- Create: `frontend/src/components/quiz/quiz-player.tsx`, `frontend/src/app/learn/[slug]/[lessonId]/quiz/[quizId]/page.tsx`

Phần này được kiểm thử bằng E2E ở Task 11.

- [x] **Bước 1: `src/components/quiz/quiz-player.tsx`**

Màn này dùng `BreakReminder` (prop `paused`) từ FE-1.

```tsx
"use client";

import { ArrowLeft, Check, ChevronLeft, ChevronRight, CloudOff, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/app/states";
import { BreakReminder } from "@/components/lesson/break-reminder";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Progress, Skeleton } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";
import type { SaveState } from "@/lib/quiz/answer-saver";
import { lastAttempt } from "@/lib/quiz/attempt-store";
import { useQuiz } from "@/lib/quiz/queries";
import { useQuizAttempt } from "@/lib/quiz/use-quiz-attempt";
import { cn } from "@/lib/utils";

/**
 * Làm quiz (design-system §5.3, phần Quiz): từng câu một, chọn đáp án bằng thẻ cả dòng (radio, ≥ 48px),
 * tự lưu và báo "Đã lưu" cạnh câu, Câu trước/Câu sau, lưới câu để nhảy nhanh, Nộp bài có xác nhận
 * khi còn câu chưa trả lời.
 */
export function QuizPlayer({ slug, lessonId, quizId }: { slug: string; lessonId: string; quizId: string }) {
  const router = useRouter();
  const quiz = useQuiz(quizId);
  const { attempt, answers, saveStates, select, submit } = useQuizAttempt(quizId);
  const [index, setIndex] = React.useState(0);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const lessonHref = `/learn/${slug}/${lessonId}`;

  if (attempt.isError) {
    const err = attempt.error;
    if (err instanceof ApiError && err.code === "QUIZ_ATTEMPT_LIMIT") {
      const last = lastAttempt.get(quizId);
      return (
        <Shell title={quiz.data?.title} lessonHref={lessonHref}>
          <div className="mx-auto max-w-md rounded-lg border p-6 text-center">
            <p className="font-medium">Bạn đã dùng hết số lần làm quiz này.</p>
            <div className="mt-4 flex flex-col justify-center gap-2 sm:flex-row">
              {last && last.status !== "in_progress" ? (
                <Button asChild>
                  <Link href={`${lessonHref}/quiz/${quizId}/result/${last.attemptId}`}>Xem kết quả gần nhất</Link>
                </Button>
              ) : null}
              <Button asChild variant="outline">
                <Link href={lessonHref}>Về bài học</Link>
              </Button>
            </div>
          </div>
        </Shell>
      );
    }
    return (
      <Shell title={quiz.data?.title} lessonHref={lessonHref}>
        <ErrorState error={err} onRetry={() => attempt.refetch()} />
      </Shell>
    );
  }

  if (attempt.isPending)
    return (
      <Shell title={quiz.data?.title} lessonHref={lessonHref}>
        <div className="space-y-4" aria-busy="true" aria-label="Đang mở bài làm">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-24 w-full" />
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      </Shell>
    );

  const questions = attempt.data.questions;
  const q = questions[Math.min(index, questions.length - 1)];
  const answeredCount = questions.filter((x) => answers[x.id]).length;
  const unanswered = questions.length - answeredCount;
  const isLast = index === questions.length - 1;

  async function doSubmit() {
    setSubmitting(true);
    try {
      const result = await submit();
      router.replace(`${lessonHref}/quiz/${quizId}/result/${result.attempt_id}`);
    } catch (err) {
      toast.error(errorMessage(err));
      setSubmitting(false);
      throw err; // giữ hộp xác nhận mở
    }
  }

  return (
    <Shell title={quiz.data?.title} lessonHref={lessonHref}>
      <div className="grid gap-8 lg:grid-cols-[1fr_220px]">
        <section aria-labelledby="q-stem">
          <div className="mb-4 flex items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>
              Câu {index + 1}/{questions.length}
            </span>
            <SaveBadge state={saveStates[q.id]} />
          </div>
          <Progress value={(answeredCount / questions.length) * 100} label={`Đã trả lời ${answeredCount}/${questions.length} câu`} />

          <fieldset className="mt-6">
            <legend id="q-stem" className="reader mb-4 text-lg font-medium [--reader-size:18px]">
              {q.stem}
            </legend>
            <div className="space-y-3">
              {q.options.map((o) => {
                const checked = answers[q.id] === o.id;
                return (
                  <label
                    key={o.id}
                    className={cn(
                      "flex min-h-12 cursor-pointer items-start gap-3 rounded-lg border bg-surface px-4 py-3 transition-colors duration-150 hover:border-primary/60",
                      "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
                      checked && "border-primary bg-primary/10",
                    )}
                  >
                    <input
                      type="radio"
                      name={`q-${q.id}`}
                      value={o.id}
                      checked={checked}
                      onChange={() => select(q.id, o.id)}
                      className="sr-only"
                    />
                    <span
                      aria-hidden
                      className={cn(
                        "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border text-xs font-semibold",
                        checked && "border-primary bg-primary text-primary-foreground",
                      )}
                    >
                      {o.id}
                    </span>
                    <span className="reader [--reader-size:16px]">{o.text}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
            <Button variant="outline" disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>
              <ChevronLeft /> Câu trước
            </Button>
            {isLast ? (
              <Button size="lg" onClick={() => setConfirmOpen(true)}>
                <Send /> Nộp bài
              </Button>
            ) : (
              <Button variant="outline" onClick={() => setIndex((i) => i + 1)}>
                Câu sau <ChevronRight />
              </Button>
            )}
          </div>
        </section>

        <aside aria-label="Danh sách câu hỏi">
          <p className="mb-2 text-sm text-muted-foreground">
            Đã trả lời {answeredCount}/{questions.length}
          </p>
          <ol className="grid grid-cols-6 gap-2 lg:grid-cols-5">
            {questions.map((x, i) => (
              <li key={x.id}>
                <button
                  type="button"
                  onClick={() => setIndex(i)}
                  aria-current={i === index ? "step" : undefined}
                  aria-label={`Câu ${i + 1}${answers[x.id] ? ", đã trả lời" : ", chưa trả lời"}`}
                  className={cn(
                    "grid size-11 place-items-center rounded-md border text-sm",
                    answers[x.id] && "border-primary/50 bg-primary/10",
                    i === index && "ring-2 ring-primary",
                  )}
                >
                  {i + 1}
                </button>
              </li>
            ))}
          </ol>
          {!isLast ? (
            <Button variant="outline" className="mt-4 w-full" onClick={() => setConfirmOpen(true)}>
              <Send /> Nộp bài
            </Button>
          ) : null}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Nộp bài?"
        description={
          unanswered > 0
            ? `Còn ${unanswered} câu chưa trả lời. Câu chưa trả lời được tính là sai. Sau khi nộp không sửa được nữa.`
            : "Bạn đã trả lời tất cả các câu. Sau khi nộp không sửa được nữa."
        }
        confirmLabel="Nộp bài"
        pendingLabel="Đang nộp…"
        onConfirm={doSubmit}
      />
      {/* quiz có giờ (tầng B1) thì không nhắc nghỉ giữa chừng */}
      <BreakReminder paused={!!attempt.data.deadline_at || submitting} />
    </Shell>
  );
}

function SaveBadge({ state }: { state: SaveState | undefined }) {
  if (!state) return null;
  const map = {
    saving: { icon: <Loader2 className="size-3.5 animate-spin" aria-hidden />, text: "Đang lưu…", cls: "" },
    saved: { icon: <Check className="size-3.5" aria-hidden />, text: "Đã lưu", cls: "text-success" },
    error: { icon: <CloudOff className="size-3.5" aria-hidden />, text: "Chưa lưu được, sẽ gửi khi nộp", cls: "text-destructive" },
  }[state];
  return (
    <span aria-live="polite" className={cn("flex items-center gap-1", map.cls)}>
      {map.icon}
      {map.text}
    </span>
  );
}

function Shell({ title, lessonHref, children }: { title?: string; lessonHref: string; children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/95 px-2 backdrop-blur md:px-4">
        <Button asChild variant="ghost" size="icon" aria-label="Về bài học">
          <Link href={lessonHref}>
            <ArrowLeft />
          </Link>
        </Button>
        <h1 className="min-w-0 flex-1 truncate font-semibold">{title ?? "Quiz"}</h1>
      </header>
      <main id="main" className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 md:px-8">
        {children}
      </main>
    </div>
  );
}
```

- [x] **Bước 2: Trang** (`src/app/learn/[slug]/[lessonId]/quiz/[quizId]/page.tsx`)

```tsx
"use client";

import { useParams } from "next/navigation";
import { QuizPlayer } from "@/components/quiz/quiz-player";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function QuizPage() {
  const { slug, lessonId, quizId } = useParams<{ slug: string; lessonId: string; quizId: string }>();
  return (
    <RequireAuth>
      <QuizPlayer key={quizId} slug={slug} lessonId={lessonId} quizId={quizId} />
    </RequireAuth>
  );
}
```

- [x] **Bước 3: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck
git add frontend/src && git commit -m "feat(web): quiz player page"
```

---

## Task 5: Màn kết quả quiz

**Files:**
- Create: `frontend/src/components/quiz/quiz-result.tsx`, `frontend/src/app/learn/[slug]/[lessonId]/quiz/[quizId]/result/[attemptId]/page.tsx`

- [x] **Bước 1: `src/components/quiz/quiz-result.tsx`**

```tsx
"use client";

import { ArrowLeft, CheckCircle2, CircleSlash, RotateCcw, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { useAttemptResult, useQuiz } from "@/lib/quiz/queries";
import type { AttemptResult } from "@/lib/quiz/types";
import { cn } from "@/lib/utils";

/**
 * Kết quả quiz: điểm, đạt/chưa đạt (icon + chữ, không chỉ màu), từng câu có đáp án đúng và giải thích.
 * Câu sai mở sẵn giải thích; có bộ lọc "Chỉ câu sai" cho buổi ôn dài.
 */
export function QuizResult({ slug, lessonId, quizId, attemptId }: { slug: string; lessonId: string; quizId: string; attemptId: string }) {
  const result = useAttemptResult(attemptId);
  const quiz = useQuiz(quizId);
  const [onlyWrong, setOnlyWrong] = React.useState(false);
  const lessonHref = `/learn/${slug}/${lessonId}`;

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/95 px-2 backdrop-blur md:px-4">
        <Button asChild variant="ghost" size="icon" aria-label="Về bài học">
          <Link href={lessonHref}>
            <ArrowLeft />
          </Link>
        </Button>
        <p className="min-w-0 flex-1 truncate font-semibold">{quiz.data?.title ?? "Kết quả quiz"}</p>
      </header>
      <main id="main" className="mx-auto w-full max-w-3xl px-4 pb-16 pt-6 md:px-8">
        {result.isPending ? (
          <div className="space-y-4" aria-busy="true" aria-label="Đang tải kết quả">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : result.isError ? (
          <ErrorState error={result.error} onRetry={() => result.refetch()} />
        ) : (
          <>
            <Summary r={result.data} />
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" checked={onlyWrong} onChange={(e) => setOnlyWrong(e.target.checked)} className="size-4 accent-[var(--primary)]" />
                Chỉ xem câu sai ({result.data.total - result.data.correct_count})
              </label>
              <div className="flex flex-col gap-2 sm:flex-row">
                {quiz.data && quiz.data.attempts_used != null && quiz.data.attempts_used < quiz.data.max_attempts ? (
                  <Button asChild variant="outline">
                    <Link href={`${lessonHref}/quiz/${quizId}`}>
                      <RotateCcw /> Làm lại ({quiz.data.max_attempts - quiz.data.attempts_used} lượt còn lại)
                    </Link>
                  </Button>
                ) : null}
                <Button asChild>
                  <Link href={lessonHref}>Về bài học</Link>
                </Button>
              </div>
            </div>
            <ol className="mt-6 space-y-4">
              {result.data.questions.map((q, i) =>
                onlyWrong && q.is_correct ? null : <ResultItem key={q.id} q={q} n={i + 1} />,
              )}
            </ol>
          </>
        )}
      </main>
    </div>
  );
}

function Summary({ r }: { r: AttemptResult }) {
  return (
    <section aria-labelledby="result-title" className="rounded-lg border bg-surface p-6">
      <h1 id="result-title" className="text-sm font-medium text-muted-foreground">
        Kết quả lần làm {r.attempt_no}
      </h1>
      <div className="mt-2 flex flex-wrap items-end gap-4">
        <p className="text-5xl font-semibold tabular-nums">{formatScore(r.score)}</p>
        <p className="pb-1 text-muted-foreground">
          {r.correct_count}/{r.total} câu đúng
        </p>
        <Badge tone={r.passed ? "success" : "destructive"} className="mb-1.5 text-sm">
          {r.passed ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
          {r.passed ? "Đạt" : "Chưa đạt"}
        </Badge>
      </div>
      {r.status === "timed_out" ? <p className="mt-2 text-sm text-muted-foreground">Bài được tự nộp khi hết giờ.</p> : null}
    </section>
  );
}

function ResultItem({ q, n }: { q: AttemptResult["questions"][number]; n: number }) {
  const unanswered = q.selected_option_id == null;
  return (
    <li className="rounded-lg border bg-surface p-4">
      <div className="flex items-start gap-2">
        {q.is_correct ? (
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-hidden />
        ) : unanswered ? (
          <CircleSlash className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <XCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted-foreground">
            Câu {n} · {q.is_correct ? "Đúng" : unanswered ? "Chưa trả lời" : "Sai"}
          </p>
          <p className="reader mt-1 font-medium [--reader-size:16px]">{q.stem}</p>
          <ul className="mt-3 space-y-1.5">
            {q.options.map((o) => {
              const correct = o.id === q.correct_option_id;
              const chosen = o.id === q.selected_option_id;
              return (
                <li
                  key={o.id}
                  className={cn(
                    "flex items-start gap-2 rounded-md border px-3 py-2 text-sm",
                    correct && "border-success/60 bg-success/10",
                    chosen && !correct && "border-destructive/60 bg-destructive/10",
                  )}
                >
                  <span className="font-semibold">{o.id}.</span>
                  <span className="flex-1">{o.text}</span>
                  {correct ? (
                    <span className="flex shrink-0 items-center gap-1 font-medium">
                      <CheckCircle2 className="size-4 text-success" aria-hidden /> Đáp án đúng
                    </span>
                  ) : null}
                  {chosen && !correct ? (
                    <span className="flex shrink-0 items-center gap-1 font-medium">
                      <XCircle className="size-4 text-destructive" aria-hidden /> Bạn chọn
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {q.explanation ? (
            <details className="mt-3" open={!q.is_correct}>
              <summary className="cursor-pointer text-sm font-medium text-primary underline-offset-4 hover:underline">
                Giải thích
              </summary>
              <p className="reader mt-2 text-muted-foreground [--reader-size:15px]">{q.explanation}</p>
            </details>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function formatScore(score: number) {
  return `${Number.isInteger(score) ? score : score.toFixed(1)}%`;
}
```

- [x] **Bước 2: Trang** (`src/app/learn/[slug]/[lessonId]/quiz/[quizId]/result/[attemptId]/page.tsx`)

```tsx
"use client";

import { useParams } from "next/navigation";
import { QuizResult } from "@/components/quiz/quiz-result";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function QuizResultPage() {
  const { slug, lessonId, quizId, attemptId } = useParams<{ slug: string; lessonId: string; quizId: string; attemptId: string }>();
  return (
    <RequireAuth>
      <QuizResult slug={slug} lessonId={lessonId} quizId={quizId} attemptId={attemptId} />
    </RequireAuth>
  );
}
```

- [x] **Bước 3: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm run build
git add frontend/src && git commit -m "feat(web): quiz result page"
```

Expected: build liệt kê `ƒ /learn/[slug]/[lessonId]/quiz/[quizId]` và `…/result/[attemptId]`.

---

## Task 6: Quiz trong trang bài học

**Files:**
- Create: `frontend/src/components/lesson/lesson-quizzes.tsx`
- Modify: `frontend/src/components/lesson/lesson-view.tsx`, `frontend/e2e/mock-api.ts`

- [x] **Bước 1: `src/components/lesson/lesson-quizzes.tsx`**

```tsx
"use client";

import { ClipboardCheck, Play, RotateCcw } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { lastAttempt } from "@/lib/quiz/attempt-store";
import { useLessonQuizzes } from "@/lib/quiz/queries";
import { formatScore } from "@/components/quiz/quiz-result";

/**
 * Quiz của bài, hiện dưới nội dung bài học. Học viên chỉ thấy quiz đã xuất bản (backend lọc).
 * Lỗi tải không chặn trang học: chỉ hiện một dòng nhỏ.
 */
export function LessonQuizzes({ slug, lessonId, isStudent }: { slug: string; lessonId: string; isStudent: boolean }) {
  const quizzes = useLessonQuizzes(lessonId);
  if (quizzes.isPending) return <Skeleton className="mt-10 h-20 w-full" />;
  if (quizzes.isError) return <p className="mt-10 text-sm text-muted-foreground">Không tải được danh sách quiz của bài.</p>;
  const items = quizzes.data.items;
  if (!items.length) return null;

  return (
    <section aria-labelledby="lesson-quizzes" className="mt-10">
      <h2 id="lesson-quizzes" className="flex items-center gap-2 text-lg font-semibold">
        <ClipboardCheck className="size-5 text-accent" aria-hidden /> Kiểm tra nhanh
      </h2>
      <ul className="mt-3 space-y-3">
        {items.map((q) => {
          const base = `/learn/${slug}/${lessonId}/quiz/${q.id}`;
          const last = isStudent ? lastAttempt.get(q.id) : null;
          const used = q.attempts_used ?? 0;
          const left = q.max_attempts - used;
          const inProgress = last?.status === "in_progress";
          return (
            <li key={q.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{q.title}</p>
                <p className="text-sm text-muted-foreground">
                  {q.question_count} câu · đạt từ {q.pass_score}%
                  {isStudent ? ` · đã làm ${used}/${q.max_attempts} lượt` : ""}
                </p>
              </div>
              {!isStudent ? (
                <Badge tone={q.status === "published" ? "success" : "neutral"}>
                  {q.status === "published" ? "Đã xuất bản" : "Nháp"}
                </Badge>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {last && last.status !== "in_progress" && last.score != null ? (
                    <Button asChild variant="link">
                      <Link href={`${base}/result/${last.attemptId}`}>Điểm gần nhất {formatScore(last.score)}</Link>
                    </Button>
                  ) : null}
                  {inProgress || left > 0 ? (
                    <Button asChild variant="outline">
                      <Link href={base}>
                        {inProgress ? <Play /> : used > 0 ? <RotateCcw /> : <Play />}
                        {inProgress ? "Làm tiếp" : used > 0 ? "Làm lại" : "Làm bài"}
                      </Link>
                    </Button>
                  ) : (
                    <span className="text-sm text-muted-foreground">Đã hết lượt</span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
```

- [x] **Bước 2: Sửa `src/components/lesson/lesson-view.tsx`** (3 chỗ)

(a) Thêm import ngay dưới dòng `import { BreakReminder } from "./break-reminder";`:

```tsx
import { LessonQuizzes } from "./lesson-quizzes";
```

(b) Hiện quiz ngay **trước** `<LessonFooter`, tức là sau phần nội dung Markdown:

```tsx
                <LessonQuizzes slug={slug} lessonId={lessonId} isStudent={isStudent} />

                <LessonFooter
```

(c) Trong `markDone()` của `LessonFooter`, thay dòng `toast.success("Đã đánh dấu học xong");` bằng comment sau. Toast ở góc dưới phải che mất nút "Bài tiếp", và đoạn quiz mới làm trang dài hơn nên E2E bắt được lỗi này:

```tsx
      // không bật toast: dòng "Đã học xong bài này" đã báo, và toast góc dưới phải sẽ che nút "Bài tiếp"
```

- [x] **Bước 3: Sửa `e2e/mock-api.ts`**

Thêm handler mặc định (ngay trước `...opts.extra,`) để các kịch bản FE-1 không gặp lỗi `UNMOCKED`:

```ts
    "GET /quizzes": (r) => json(r, { items: [], total: 0, page: 1, size: 50 }),
```

- [x] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend/src frontend/e2e/mock-api.ts && git commit -m "feat(web): list lesson quizzes on the lesson page"
```

---

## Task 7: Thanh tab soạn bài và khung trang con

**Files:**
- Create: `frontend/src/components/teach/lesson-tabs.tsx`, `frontend/src/components/teach/lesson-subpage.tsx`
- Modify: `frontend/src/components/teach/lesson-editor.tsx`, `frontend/src/components/teach/lesson-editor.test.tsx`

- [x] **Bước 1: `src/components/teach/lesson-tabs.tsx`**

```tsx
"use client";

import { ClipboardCheck, FileText, ListChecks } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

/** Thanh chuyển giữa 3 phần soạn một bài: Nội dung | Câu hỏi | Quiz (mỗi phần một trang riêng). */
export function LessonTabs({ slug, lessonId }: { slug: string; lessonId: string }) {
  const pathname = usePathname();
  const base = `/teach/${slug}/lessons/${lessonId}`;
  const tabs = [
    { href: base, label: "Nội dung", icon: FileText },
    { href: `${base}/questions`, label: "Câu hỏi", icon: ListChecks },
    { href: `${base}/quizzes`, label: "Quiz", icon: ClipboardCheck },
  ];
  return (
    <nav aria-label="Phần soạn bài" className="mb-6 flex gap-1 overflow-x-auto border-b">
      {tabs.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px flex h-11 shrink-0 items-center gap-2 border-b-2 border-transparent px-3 text-sm transition-colors duration-150 hover:text-primary",
              active ? "border-primary font-medium text-primary" : "text-muted-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [x] **Bước 2: `src/components/teach/lesson-subpage.tsx`**

```tsx
"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Skeleton } from "@/components/ui/misc";
import { useCourse, useLesson } from "@/lib/queries";
import { LessonTabs } from "./lesson-tabs";

/** Khung chung cho trang Câu hỏi / Quiz của một bài trong trình soạn. */
export function LessonSubpage({ slug, lessonId, children }: { slug: string; lessonId: string; children: React.ReactNode }) {
  const course = useCourse(slug);
  const lesson = useLesson(lessonId);
  return (
    <div className="mx-auto max-w-4xl">
      <Link href={`/teach/${slug}`} className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {course.data?.title ?? "Khóa học"}
      </Link>
      {lesson.data ? (
        <h1 className="mb-4 text-2xl font-semibold md:text-3xl">{lesson.data.title}</h1>
      ) : (
        <Skeleton className="mb-4 h-9 w-2/3" />
      )}
      <LessonTabs slug={slug} lessonId={lessonId} />
      {children}
    </div>
  );
}
```

- [x] **Bước 3: Gắn tab vào trình soạn nội dung** (`lesson-editor.tsx`)

Thêm import `import { LessonTabs } from "./lesson-tabs";`. Trong `LessonEditor`, bọc phần `return` trong fragment để thanh tab nằm phía trên lưới 3 cột:

```tsx
  return (
    <>
      <LessonTabs slug={slug} lessonId={lessonId} />
      <div className="grid gap-6 lg:grid-cols-[240px_1fr_320px]">
        {/* … giữ nguyên toàn bộ nội dung cũ của lưới … */}
      </div>
    </>
  );
```

- [x] **Bước 4: Sửa mock trong `lesson-editor.test.tsx`**

`LessonTabs` dùng `usePathname`, nên mock `next/navigation` phải có thêm hàm này. Thay dòng `vi.mock("next/navigation", …)` bằng:

```tsx
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/teach/toan/lessons/l1", // thanh LessonTabs (FE-2)
}));
```

Run: `npx vitest run src/components/teach`
Expected: PASS. Nếu quên bước này, 4 test của `lesson-editor.test.tsx` sẽ fail với lỗi `No "usePathname" export is defined on the "next/navigation" mock`.

- [x] **Bước 5: Commit**

```bash
git add frontend/src && git commit -m "feat(web): lesson editor tabs for content, questions and quizzes"
```

---

## Task 8: Ngân hàng câu hỏi (sinh bằng AI và duyệt)

**Files:**
- Create: `frontend/src/components/teach/question-card.tsx`, `frontend/src/components/teach/question-bank.tsx`, `frontend/src/app/(main)/teach/[slug]/lessons/[lessonId]/questions/page.tsx`

- [x] **Bước 1: `src/components/teach/question-card.tsx`**

Form sửa hiện câu lỗi 422 của backend ngay tại chỗ.

```tsx
"use client";

import { AlertTriangle, Check, CheckCircle2, Pencil, RotateCcw, X } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { DIFFICULTY_LABEL, type Difficulty, type Question } from "@/lib/quiz/types";
import { cn } from "@/lib/utils";

const STATUS_BADGE = {
  pending: { label: "Chờ duyệt", tone: "accent" },
  approved: { label: "Đã duyệt", tone: "success" },
  edited: { label: "Đã sửa và duyệt", tone: "success" },
  rejected: { label: "Đã loại", tone: "neutral" },
} as const;

export type ReviewAction =
  | { action: "approve" }
  | { action: "reject" }
  | {
      action: "edit";
      stem: string;
      options: { id: string; text: string }[];
      correct_option_id: string;
      explanation: string;
      difficulty: Difficulty;
    };

/**
 * Một câu hỏi trong màn duyệt (design-system §5.3: Duyệt = Chính, Sửa / Loại = Phụ).
 * Hiện đáp án đúng bằng icon + chữ, cảnh báo khi AI tự kiểm tra thấy nghi vấn, và đoạn tài liệu nguồn.
 */
export function QuestionCard({
  q,
  n,
  onReview,
  busy,
}: {
  q: Question;
  n: number;
  onReview: (a: ReviewAction) => Promise<unknown>;
  busy: boolean;
}) {
  const [editing, setEditing] = React.useState(false);
  const status = STATUS_BADGE[q.review_status];

  return (
    <article aria-labelledby={`q-${q.id}`} className="rounded-lg border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium text-muted-foreground">Câu {n}</span>
        <Badge tone={status.tone}>{status.label}</Badge>
        <Badge>{DIFFICULTY_LABEL[q.difficulty]}</Badge>
        <Badge>{q.origin === "ai" ? "AI sinh" : "Thủ công"}</Badge>
        {q.self_check_flag ? (
          <Badge tone="destructive">
            <AlertTriangle className="size-3" aria-hidden /> AI tự kiểm tra thấy nghi vấn
          </Badge>
        ) : null}
      </div>

      {editing ? (
        <EditForm
          q={q}
          onCancel={() => setEditing(false)}
          onSave={async (a) => {
            await onReview(a);
            setEditing(false);
          }}
        />
      ) : (
        <>
          <p id={`q-${q.id}`} className="reader mt-3 font-medium [--reader-size:16px]">
            {q.stem}
          </p>
          <ul className="mt-3 space-y-1.5">
            {q.options.map((o) => {
              const correct = o.id === q.correct_option_id;
              return (
                <li
                  key={o.id}
                  className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm", correct && "border-success/60 bg-success/10")}
                >
                  <span className="font-semibold">{o.id}.</span>
                  <span className="flex-1">{o.text}</span>
                  {correct ? (
                    <span className="flex shrink-0 items-center gap-1 font-medium">
                      <CheckCircle2 className="size-4 text-success" aria-hidden /> Đáp án đúng
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {q.explanation ? <p className="mt-3 text-sm text-muted-foreground">Giải thích: {q.explanation}</p> : null}
          {q.source_excerpt ? (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-primary underline-offset-4 hover:underline">
                Đoạn tài liệu nguồn{q.source_page_no ? ` (trang ${q.source_page_no})` : ""}
              </summary>
              <p className="mt-2 whitespace-pre-line rounded-md bg-muted p-3 text-muted-foreground">{q.source_excerpt}</p>
            </details>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-2">
            {q.review_status === "pending" ? (
              <Button size="sm" className="h-10 md:h-8" loading={busy} loadingText="Đang duyệt…" onClick={() => onReview({ action: "approve" })}>
                <Check /> Duyệt
              </Button>
            ) : null}
            {q.review_status === "rejected" ? (
              <Button size="sm" variant="outline" className="h-10 md:h-8" loading={busy} loadingText="Đang khôi phục…" onClick={() => onReview({ action: "approve" })}>
                <RotateCcw /> Khôi phục và duyệt
              </Button>
            ) : (
              <>
                <Button size="sm" variant="outline" className="h-10 md:h-8" disabled={busy} onClick={() => setEditing(true)}>
                  <Pencil /> Sửa
                </Button>
                <Button size="sm" variant="outline" className="h-10 md:h-8" disabled={busy} onClick={() => onReview({ action: "reject" })}>
                  <X /> Loại
                </Button>
              </>
            )}
          </div>
        </>
      )}
    </article>
  );
}

function EditForm({
  q,
  onCancel,
  onSave,
}: {
  q: Question;
  onCancel: () => void;
  onSave: (a: ReviewAction) => Promise<void>;
}) {
  const [stem, setStem] = React.useState(q.stem);
  const [options, setOptions] = React.useState(q.options.map((o) => ({ ...o })));
  const [correct, setCorrect] = React.useState(q.correct_option_id);
  const [explanation, setExplanation] = React.useState(q.explanation);
  const [difficulty, setDifficulty] = React.useState<Difficulty>(q.difficulty);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await onSave({ action: "edit", stem, options, correct_option_id: correct, explanation, difficulty });
    } catch (err) {
      // 422: luật câu hỏi (đúng 4 lựa chọn khác nhau, đề ≥ 10 ký tự…) — hiện câu backend trả về
      const detail = err instanceof ApiError ? (err.details.errors as { msg: string }[] | undefined)?.[0]?.msg : undefined;
      setError(detail ? `${errorMessage(err)}: ${detail}` : errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-4">
      <Field id={`stem-${q.id}`} label="Đề bài">
        <Textarea rows={3} value={stem} maxLength={1000} onChange={(e) => setStem(e.target.value)} />
      </Field>
      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium">Các lựa chọn (chọn ô tròn ở đáp án đúng)</legend>
        {options.map((o, i) => (
          <div key={o.id} className="flex items-center gap-2">
            <input
              type="radio"
              name={`correct-${q.id}`}
              checked={correct === o.id}
              onChange={() => setCorrect(o.id)}
              aria-label={`Đáp án đúng là ${o.id}`}
              className="size-5 accent-[var(--primary)]"
            />
            <span className="w-5 font-semibold">{o.id}.</span>
            <Input
              aria-label={`Lựa chọn ${o.id}`}
              value={o.text}
              maxLength={300}
              onChange={(e) => setOptions((prev) => prev.map((p, j) => (j === i ? { ...p, text: e.target.value } : p)))}
            />
          </div>
        ))}
      </fieldset>
      <Field id={`exp-${q.id}`} label="Giải thích">
        <Textarea rows={2} value={explanation} maxLength={2000} onChange={(e) => setExplanation(e.target.value)} />
      </Field>
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Độ khó</legend>
        <div className="inline-flex rounded-md border p-0.5">
          {(["easy", "medium", "hard"] as const).map((d) => (
            <label
              key={d}
              className={cn(
                "flex h-9 cursor-pointer items-center rounded px-3 text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                difficulty === d && "bg-primary text-primary-foreground",
              )}
            >
              <input type="radio" name={`diff-${q.id}`} className="sr-only" checked={difficulty === d} onChange={() => setDifficulty(d)} />
              {DIFFICULTY_LABEL[d]}
            </label>
          ))}
        </div>
      </fieldset>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={pending}>
          Hủy
        </Button>
        <Button type="submit" loading={pending} loadingText="Đang lưu…">
          Lưu và duyệt
        </Button>
      </div>
    </form>
  );
}
```

- [x] **Bước 2: `src/components/teach/question-bank.tsx`**

```tsx
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ListChecks, Loader2, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { quizKeys, useGenerateQuestions, useJob, useLessonQuestions, useReviewQuestion } from "@/lib/quiz/queries";
import type { Question } from "@/lib/quiz/types";
import { cn } from "@/lib/utils";
import { QuestionCard, type ReviewAction } from "./question-card";

const TABS = [
  { key: "pending", label: "Chờ duyệt", match: (q: Question) => q.review_status === "pending" },
  { key: "approved", label: "Đã duyệt", match: (q: Question) => q.review_status === "approved" || q.review_status === "edited" },
  { key: "rejected", label: "Đã loại", match: (q: Question) => q.review_status === "rejected" },
] as const;

const MIXES = {
  balanced: { label: "Cân bằng", value: { easy: 0.3, medium: 0.5, hard: 0.2 } },
  easier: { label: "Dễ hơn", value: { easy: 0.5, medium: 0.4, hard: 0.1 } },
  harder: { label: "Khó hơn", value: { easy: 0.1, medium: 0.4, hard: 0.5 } },
} as const;

const UNDO_MS = 5000;

/** Ngân hàng câu hỏi của một bài: sinh bằng AI (job nền) và duyệt / sửa / loại từng câu. */
export function QuestionBank({ lessonId }: { lessonId: string }) {
  const questions = useLessonQuestions(lessonId, "all");
  const review = useReviewQuestion(lessonId);
  const [tab, setTab] = React.useState<(typeof TABS)[number]["key"]>("pending");
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [hidden, setHidden] = React.useState<Set<string>>(new Set()); // đang chờ 5 giây để "Hoàn tác" loại
  const timers = React.useRef(new Map<string, number>());

  const send = React.useCallback(
    async (id: string, a: ReviewAction) => {
      setBusyId(id);
      try {
        await review.mutateAsync({ id, body: a });
      } finally {
        setBusyId(null);
      }
    },
    [review],
  );

  // Loại: ẩn ngay, đợi 5 giây cho "Hoàn tác" rồi mới gửi (design-system §5.3).
  const rejectWithUndo = React.useCallback(
    (q: Question) => {
      setHidden((s) => new Set(s).add(q.id));
      const unhide = () =>
        setHidden((s) => {
          const next = new Set(s);
          next.delete(q.id);
          return next;
        });
      const timer = window.setTimeout(async () => {
        timers.current.delete(q.id);
        try {
          await send(q.id, { action: "reject" });
        } catch (err) {
          toast.error(errorMessage(err));
        } finally {
          unhide();
        }
      }, UNDO_MS);
      timers.current.set(q.id, timer);
      toast("Đã loại câu hỏi", {
        duration: UNDO_MS,
        action: {
          label: "Hoàn tác",
          onClick: () => {
            window.clearTimeout(timers.current.get(q.id));
            timers.current.delete(q.id);
            unhide();
          },
        },
      });
    },
    [send],
  );

  // Rời trang khi còn câu đang chờ hoàn tác: gửi luôn, không để mất thao tác
  React.useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const [id, t] of pending) {
        window.clearTimeout(t);
        void review.mutateAsync({ id, body: { action: "reject" } }).catch(() => undefined);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onReview(q: Question, a: ReviewAction) {
    if (a.action === "reject") return rejectWithUndo(q);
    try {
      await send(q.id, a);
      toast.success(a.action === "edit" ? "Đã lưu và duyệt câu hỏi" : "Đã duyệt");
    } catch (err) {
      if (a.action === "edit") throw err; // form sửa tự hiện lỗi tại chỗ
      toast.error(errorMessage(err));
    }
  }

  const all = (questions.data?.items ?? []).filter((q) => !hidden.has(q.id));
  const current = TABS.find((t) => t.key === tab)!;
  const visible = all.filter(current.match);

  return (
    <div className="space-y-6">
      <GeneratePanel lessonId={lessonId} />

      <div role="tablist" aria-label="Lọc câu hỏi" className="flex gap-1 border-b">
        {TABS.map((t) => {
          const count = all.filter(t.match).length;
          return (
            <button
              key={t.key}
              role="tab"
              type="button"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "-mb-px h-11 border-b-2 border-transparent px-3 text-sm",
                tab === t.key ? "border-primary font-medium text-primary" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label} ({count})
            </button>
          );
        })}
      </div>

      <div role="tabpanel" aria-label={current.label}>
        {questions.isPending ? (
          <div className="space-y-3" aria-busy="true" aria-label="Đang tải câu hỏi">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : questions.isError ? (
          <ErrorState error={questions.error} onRetry={() => questions.refetch()} />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={ListChecks}
            title={tab === "pending" ? "Không có câu nào chờ duyệt. Bấm “Sinh câu hỏi bằng AI” để tạo thêm." : `Chưa có câu nào ${current.label.toLowerCase()}.`}
          />
        ) : (
          <ol className="space-y-4">
            {visible.map((q, i) => (
              <li key={q.id}>
                <QuestionCard q={q} n={i + 1} busy={busyId === q.id} onReview={(a) => onReview(q, a)} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function GeneratePanel({ lessonId }: { lessonId: string }) {
  const qc = useQueryClient();
  const generate = useGenerateQuestions(lessonId);
  const [count, setCount] = React.useState(10);
  const [mix, setMix] = React.useState<keyof typeof MIXES>("balanced");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const job = useJob(jobId);
  const status = job.data?.status;
  const running = !!jobId && status !== "done" && status !== "failed";

  // Job xong → tải lại danh sách và báo số câu chờ duyệt
  const handled = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!jobId || handled.current === jobId || (status !== "done" && status !== "failed")) return;
    handled.current = jobId;
    if (status === "done") {
      void qc.invalidateQueries({ queryKey: quizKeys.questions(lessonId) }).then(() => {
        const items = qc.getQueryData<{ items: Question[] }>(quizKeys.questionList(lessonId, "all"))?.items ?? [];
        toast.success(`AI đã soạn xong. Có ${items.filter((q) => q.review_status === "pending").length} câu chờ duyệt.`);
      });
    }
  }, [jobId, status, lessonId, qc]);

  async function start() {
    try {
      const { job_id } = await generate.mutateAsync({ count, difficulty: MIXES[mix].value });
      setJobId(job_id);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <section aria-labelledby="gen-title" className="rounded-lg border bg-surface p-4">
      <h2 id="gen-title" className="font-semibold">
        Sinh câu hỏi bằng AI
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        AI soạn câu trắc nghiệm từ tài liệu PDF đã xử lý của bài. Câu sinh ra cần bạn duyệt trước khi đưa vào quiz.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="text-sm">
          <span className="mb-1 block font-medium">Số câu</span>
          <select
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            disabled={running}
            className="h-10 rounded-md border bg-surface px-3"
          >
            {[5, 10, 15, 20].map((n) => (
              <option key={n} value={n}>
                {n} câu
              </option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend className="mb-1 text-sm font-medium">Độ khó</legend>
          <div className="inline-flex rounded-md border p-0.5">
            {(Object.keys(MIXES) as (keyof typeof MIXES)[]).map((k) => (
              <label
                key={k}
                className={cn(
                  "flex h-9 cursor-pointer items-center rounded px-3 text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                  mix === k && "bg-primary text-primary-foreground",
                )}
              >
                <input type="radio" name="mix" className="sr-only" checked={mix === k} disabled={running} onChange={() => setMix(k)} />
                {MIXES[k].label}
              </label>
            ))}
          </div>
        </fieldset>
        <Button onClick={start} loading={generate.isPending} loadingText="Đang gửi…" disabled={running}>
          <Sparkles /> Sinh câu hỏi bằng AI
        </Button>
      </div>
      <div aria-live="polite" className="mt-3 text-sm">
        {running ? (
          <p className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> AI đang soạn… (thường mất khoảng 1 phút). Bạn vẫn duyệt các câu khác được.
          </p>
        ) : status === "failed" ? (
          <p role="alert" className="text-destructive">
            {job.data?.error_msg ?? "Không sinh được câu hỏi. Thử lại sau."}
          </p>
        ) : null}
      </div>
    </section>
  );
}
```

- [x] **Bước 3: Trang** (`src/app/(main)/teach/[slug]/lessons/[lessonId]/questions/page.tsx`)

```tsx
"use client";

import { useParams } from "next/navigation";
import { LessonSubpage } from "@/components/teach/lesson-subpage";
import { QuestionBank } from "@/components/teach/question-bank";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function LessonQuestionsPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth staff>
      <LessonSubpage slug={slug} lessonId={lessonId}>
        <QuestionBank key={lessonId} lessonId={lessonId} />
      </LessonSubpage>
    </RequireAuth>
  );
}
```

- [x] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck
git add frontend/src && git commit -m "feat(web): AI question generation and review screen"
```

---

## Task 9: Quản lý quiz của bài

**Files:**
- Create: `frontend/src/components/teach/quiz-manager.tsx`, `frontend/src/app/(main)/teach/[slug]/lessons/[lessonId]/quizzes/page.tsx`

- [x] **Bước 1: `src/components/teach/quiz-manager.tsx`**

Hộp thoại Tạo / Sửa chỉ liệt kê câu `approved` / `edited`. Khi sửa, các câu đang có trong quiz được chọn sẵn.

```tsx
"use client";

import { ClipboardCheck, Globe, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Badge, Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { useLessonQuestions, useLessonQuizzes, useQuiz, useQuizMutations } from "@/lib/quiz/queries";
import { DIFFICULTY_LABEL, type Quiz } from "@/lib/quiz/types";

/** Quiz của một bài: tạo từ các câu đã duyệt, sửa khi còn nháp, xuất bản (có xác nhận), xóa (trong menu ⋯). */
export function QuizManager({ lessonId }: { lessonId: string }) {
  const quizzes = useLessonQuizzes(lessonId);
  const mut = useQuizMutations(lessonId);
  const [editing, setEditing] = React.useState<Quiz | "new" | null>(null);
  const [publishing, setPublishing] = React.useState<Quiz | null>(null);
  const [deleting, setDeleting] = React.useState<Quiz | null>(null);

  const createButton = (
    <Button onClick={() => setEditing("new")}>
      <Plus /> Tạo quiz
    </Button>
  );

  return (
    <section aria-labelledby="quiz-title" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="quiz-title" className="text-lg font-semibold">
          Quiz của bài
        </h2>
        {quizzes.data?.items.length ? createButton : null}
      </div>

      {quizzes.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : quizzes.isError ? (
        <ErrorState error={quizzes.error} onRetry={() => quizzes.refetch()} />
      ) : quizzes.data.items.length === 0 ? (
        <EmptyState icon={ClipboardCheck} title="Bài này chưa có quiz. Tạo quiz từ các câu hỏi đã duyệt." action={createButton} />
      ) : (
        <ul className="space-y-3">
          {quizzes.data.items.map((q) => (
            <li key={q.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{q.title}</p>
                <p className="text-sm text-muted-foreground">
                  {q.question_count} câu · tối đa {q.max_attempts} lượt · đạt từ {q.pass_score}%
                </p>
              </div>
              {q.status === "published" ? <Badge tone="success">Đã xuất bản</Badge> : <Badge>Nháp</Badge>}
              {q.status === "draft" ? (
                <>
                  <Button variant="outline" size="sm" className="h-10 md:h-8" onClick={() => setEditing(q)}>
                    <Pencil /> Sửa
                  </Button>
                  <Button size="sm" className="h-10 md:h-8" disabled={q.question_count === 0} onClick={() => setPublishing(q)}>
                    <Globe /> Xuất bản
                  </Button>
                </>
              ) : null}
              <Menu>
                <MenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label={`Thao tác với quiz ${q.title}`}>
                    <MoreHorizontal />
                  </Button>
                </MenuTrigger>
                <MenuContent>
                  <MenuItem destructive onSelect={() => setDeleting(q)}>
                    <Trash2 /> Xóa quiz
                  </MenuItem>
                </MenuContent>
              </Menu>
            </li>
          ))}
        </ul>
      )}

      {editing ? (
        <QuizDialog lessonId={lessonId} quiz={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      ) : null}

      <ConfirmDialog
        open={!!publishing}
        onOpenChange={(o) => !o && setPublishing(null)}
        title={`Xuất bản “${publishing?.title}”?`}
        description="Học viên đã đăng ký sẽ thấy và làm được quiz này. Sau khi xuất bản chỉ đổi được tiêu đề, không thêm bớt câu hỏi."
        confirmLabel="Xuất bản"
        pendingLabel="Đang xuất bản…"
        onConfirm={async () => {
          try {
            await mut.publish.mutateAsync(publishing!.id);
            toast.success("Đã xuất bản quiz");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        destructive
        title={`Xóa quiz “${deleting?.title}”?`}
        description="Câu hỏi vẫn còn trong ngân hàng câu hỏi của bài. Quiz đã có học viên làm thì không xóa được."
        confirmLabel="Xóa quiz"
        pendingLabel="Đang xóa…"
        onConfirm={async () => {
          try {
            await mut.remove.mutateAsync(deleting!.id);
            toast.success("Đã xóa quiz");
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </section>
  );
}

function QuizDialog({ lessonId, quiz, onClose }: { lessonId: string; quiz: Quiz | null; onClose: () => void }) {
  const mut = useQuizMutations(lessonId);
  const bank = useLessonQuestions(lessonId, "all");
  const detail = useQuiz(quiz?.id ?? "");
  const [title, setTitle] = React.useState(quiz?.title ?? "");
  const [maxAttempts, setMaxAttempts] = React.useState(quiz?.max_attempts ?? 1);
  const [passScore, setPassScore] = React.useState(quiz?.pass_score ?? 50);
  const [selected, setSelected] = React.useState<Set<string> | null>(quiz ? null : new Set());
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  // Sửa quiz: lấy danh sách câu đang có trong quiz làm lựa chọn ban đầu
  const chosen = selected ?? new Set((detail.data?.questions ?? []).map((q) => q.id));
  const approved = (bank.data?.items ?? []).filter((q) => q.review_status === "approved" || q.review_status === "edited");
  const loading = bank.isPending || (!!quiz && detail.isPending);

  function toggle(id: string) {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return setError("Nhập tiêu đề quiz");
    setPending(true);
    setError(null);
    const body = { title: title.trim(), max_attempts: maxAttempts, pass_score: passScore, question_ids: [...chosen] };
    try {
      if (quiz) await mut.update.mutateAsync({ id: quiz.id, body });
      else await mut.create.mutateAsync({ lesson_id: lessonId, ...body });
      toast.success(quiz ? "Đã lưu quiz" : "Đã tạo quiz (nháp)");
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={quiz ? "Sửa quiz" : "Tạo quiz"}
        description="Quiz ở dạng nháp cho tới khi bạn xuất bản."
        className="max-h-[90dvh] max-w-2xl overflow-y-auto"
      >
        <form onSubmit={submit} className="space-y-4">
          <Field id="quiz-title-input" label="Tiêu đề">
            <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="quiz-attempts" label="Số lượt làm tối đa" hint="1–20 lượt">
              <Input type="number" min={1} max={20} value={maxAttempts} onChange={(e) => setMaxAttempts(Number(e.target.value))} />
            </Field>
            <Field id="quiz-pass" label="Điểm đạt (%)" hint="0–100">
              <Input type="number" min={0} max={100} step={5} value={passScore} onChange={(e) => setPassScore(Number(e.target.value))} />
            </Field>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">
              Câu hỏi đã duyệt ({chosen.size}/{approved.length} được chọn)
            </legend>
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : approved.length === 0 ? (
              <p className="text-sm text-muted-foreground">Chưa có câu nào được duyệt. Duyệt câu hỏi ở tab “Câu hỏi” trước.</p>
            ) : (
              <ul className="max-h-72 space-y-1 overflow-y-auto rounded-md border p-2">
                {approved.map((q) => (
                  <li key={q.id}>
                    <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded px-2 py-2 hover:bg-muted">
                      <input type="checkbox" checked={chosen.has(q.id)} onChange={() => toggle(q.id)} className="mt-1 size-4 accent-[var(--primary)]" />
                      <span className="flex-1 text-sm">{q.stem}</span>
                      <Badge>{DIFFICULTY_LABEL[q.difficulty]}</Badge>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              Hủy
            </Button>
            <Button type="submit" loading={pending} loadingText="Đang lưu…">
              {quiz ? "Lưu quiz" : "Tạo quiz"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [x] **Bước 2: Trang** (`src/app/(main)/teach/[slug]/lessons/[lessonId]/quizzes/page.tsx`)

```tsx
"use client";

import { useParams } from "next/navigation";
import { LessonSubpage } from "@/components/teach/lesson-subpage";
import { QuizManager } from "@/components/teach/quiz-manager";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function LessonQuizzesPage() {
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  return (
    <RequireAuth staff>
      <LessonSubpage slug={slug} lessonId={lessonId}>
        <QuizManager key={lessonId} lessonId={lessonId} />
      </LessonSubpage>
    </RequireAuth>
  );
}
```

- [x] **Bước 3: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck
git add frontend/src && git commit -m "feat(web): create, edit, publish and delete lesson quizzes"
```

---

## Task 10: Thống kê khóa học

**Files:**
- Create: `frontend/src/components/teach/course-analytics.tsx`, `frontend/src/app/(main)/teach/[slug]/analytics/page.tsx`
- Modify: `frontend/src/components/teach/course-editor.tsx`

- [x] **Bước 1: `src/components/teach/course-analytics.tsx`**

```tsx
"use client";

import { ArrowLeft, BarChart3 } from "lucide-react";
import Link from "next/link";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { Badge, Skeleton } from "@/components/ui/misc";
import { useCourse } from "@/lib/queries";
import { useCourseAnalytics } from "@/lib/quiz/queries";

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Bảng điều khiển của giảng viên (A8). Số liệu ít, đọc nhanh: thẻ số lớn cho con số chính, bảng có thanh
 * ngang cho tỉ lệ hoàn thành / tỉ lệ đạt (một màu, giá trị luôn in bằng chữ nên không phụ thuộc màu).
 */
export function CourseAnalyticsView({ slug }: { slug: string }) {
  const course = useCourse(slug);
  const stats = useCourseAnalytics(course.data?.id);

  return (
    <>
      <Link href={`/teach/${slug}`} className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {course.data?.title ?? "Khóa học"}
      </Link>
      <PageHeader title="Thống kê khóa học" />
      {course.isError || stats.isError ? (
        <ErrorState error={course.error ?? stats.error} onRetry={() => (course.refetch(), stats.refetch())} />
      ) : !stats.data ? (
        <div className="space-y-4" aria-busy="true" aria-label="Đang tải thống kê">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-60" />
        </div>
      ) : stats.data.enrollments === 0 ? (
        <EmptyState icon={BarChart3} title="Chưa có học viên nào đăng ký khóa này, nên chưa có số liệu." />
      ) : (
        <div className="space-y-10">
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Học viên đăng ký" value={stats.data.enrollments} />
            <Tile
              label="Hoàn thành khóa"
              value={stats.data.completed_enrollments}
              note={pct(stats.data.completed_enrollments / stats.data.enrollments)}
            />
            <Tile label="Câu hỏi gửi AI Tutor" value={stats.data.tutor.questions} note={`${stats.data.tutor.sessions} phiên`} />
            <Tile
              label="AI từ chối trả lời"
              value={stats.data.tutor.refused_answers}
              note={stats.data.tutor.questions ? pct(stats.data.tutor.refused_answers / stats.data.tutor.questions) : undefined}
            />
          </dl>

          <section aria-labelledby="lesson-stats">
            <h2 id="lesson-stats" className="mb-3 text-lg font-semibold">
              Tỉ lệ hoàn thành từng bài
            </h2>
            <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng tỉ lệ hoàn thành từng bài">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Bài học</th>
                    <th className="px-4 py-2 font-medium">Hoàn thành</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.data.lessons.map((l) => (
                    <tr key={l.lesson_id} className="border-b last:border-b-0">
                      <td className="px-4 py-2.5">
                        <span className="block">{l.title}</span>
                        <span className="text-xs text-muted-foreground">{l.section_title}</span>
                      </td>
                      <td className="w-1/2 px-4 py-2.5">
                        <Meter value={l.completion_rate} label={`${l.done_count}/${stats.data.enrollments} · ${pct(l.completion_rate)}`} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="quiz-stats">
            <h2 id="quiz-stats" className="mb-3 text-lg font-semibold">
              Quiz
            </h2>
            {stats.data.quizzes.length === 0 ? (
              <p className="text-sm text-muted-foreground">Khóa chưa có quiz nào.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng thống kê quiz">
                <table className="w-full min-w-[560px] text-sm">
                  <thead className="border-b text-left text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 font-medium">Quiz</th>
                      <th className="px-4 py-2 font-medium">Bài nộp</th>
                      <th className="px-4 py-2 font-medium">Học viên</th>
                      <th className="px-4 py-2 font-medium">Điểm TB</th>
                      <th className="px-4 py-2 font-medium">Tỉ lệ đạt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.data.quizzes.map((q) => (
                      <tr key={q.quiz_id} className="border-b last:border-b-0">
                        <td className="px-4 py-2.5">
                          {q.title} {q.status === "draft" ? <Badge className="ml-1">Nháp</Badge> : null}
                        </td>
                        <td className="px-4 py-2.5 tabular-nums">{q.attempts}</td>
                        <td className="px-4 py-2.5 tabular-nums">{q.students}</td>
                        <td className="px-4 py-2.5 tabular-nums">{q.avg_score == null ? "—" : `${q.avg_score.toFixed(1)}%`}</td>
                        <td className="w-1/3 px-4 py-2.5">
                          {q.pass_rate == null ? "—" : <Meter value={q.pass_rate} label={pct(q.pass_rate)} />}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function Tile({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="rounded-lg border bg-surface p-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="mt-1 flex items-baseline gap-2">
        <span className="text-3xl font-semibold tabular-nums">{value}</span>
        {note ? <span className="text-sm text-muted-foreground">{note}</span> : null}
      </dd>
    </div>
  );
}

/** Thanh ngang một màu; con số luôn in kèm nên không phụ thuộc màu (dataviz: text dùng màu chữ, không dùng màu thanh). */
function Meter({ value, label }: { value: number; label: string }) {
  const v = Math.min(1, Math.max(0, value));
  return (
    <div className="flex items-center gap-3" title={label}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className="h-full rounded-full bg-accent" style={{ width: `${v * 100}%` }} />
      </div>
      <span className="w-24 shrink-0 text-right tabular-nums">{label}</span>
    </div>
  );
}
```

- [x] **Bước 2: Trang** (`src/app/(main)/teach/[slug]/analytics/page.tsx`)

```tsx
"use client";

import { useParams } from "next/navigation";
import { CourseAnalyticsView } from "@/components/teach/course-analytics";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function CourseAnalyticsPage() {
  const { slug } = useParams<{ slug: string }>();
  return (
    <RequireAuth staff>
      <CourseAnalyticsView slug={slug} />
    </RequireAuth>
  );
}
```

- [x] **Bước 3: Nút "Thống kê" trong trình soạn khóa** (`course-editor.tsx`)

Thêm `BarChart3` vào import `lucide-react`. Ở thanh trên cùng, chèn nút này ngay **trước** khối `{firstLesson ? (` (nút "Xem như học viên"):

```tsx
        <Button asChild variant="outline">
          <Link href={`/teach/${course.slug}/analytics`}>
            <BarChart3 /> Thống kê
          </Link>
        </Button>
```

Đây là nút phụ, nên nút chính duy nhất của thanh vẫn là "Xuất bản".

- [x] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test && npm run build
git add frontend/src && git commit -m "feat(web): course analytics dashboard for teachers"
```

Expected: build có thêm các route `ƒ /teach/[slug]/analytics`, `…/lessons/[lessonId]/questions` và `…/lessons/[lessonId]/quizzes`.

---

## Task 11: E2E cho quiz, duyệt câu hỏi và thống kê

**Files:**
- Create: `frontend/e2e/quiz-data.ts`, `frontend/e2e/quiz.spec.ts`, `frontend/e2e/teacher-quiz.spec.ts`

- [ ] **Bước 1: Dữ liệu giả** (`e2e/quiz-data.ts`)

```ts
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
```

- [ ] **Bước 2: Kịch bản học viên** (`e2e/quiz.spec.ts`)

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { L1, mockApi } from "./mock-api";
import { ATTEMPT_ID, attempt, QUIZ_ID, quiz, result } from "./quiz-data";

test.describe("học viên làm quiz", () => {
  test("mở quiz từ bài học → chọn đáp án (tự lưu) → nộp có xác nhận → xem kết quả và giải thích", async ({ page }) => {
    const saved: Record<string, string> = {};
    let submitted: { final_answers: { question_id: string; selected_option_id: string }[] } | null = null;
    let used = 0;
    await mockApi(page, {
      extra: {
        "GET /quizzes": (r) => r.fulfill({ json: { items: [quiz({ attempts_used: used })], total: 1, page: 1, size: 50 } }),
        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz({ attempts_used: used }) }),
        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) => r.fulfill({ status: 201, json: attempt() }),
        [`PUT /attempts/${ATTEMPT_ID}/answers/*`]: async (r, url) => {
          const qid = url.pathname.split("/").pop()!;
          saved[qid] = r.request().postDataJSON().selected_option_id;
          await r.fulfill({ json: { question_id: qid, selected_option_id: saved[qid], answered_at: "2026-10-06T00:01:00Z" } });
        },
        [`POST /attempts/${ATTEMPT_ID}/submit`]: (r) => {
          submitted = r.request().postDataJSON();
          used = 1;
          const answers = Object.fromEntries(submitted!.final_answers.map((a) => [a.question_id, a.selected_option_id]));
          return r.fulfill({ json: result(answers) });
        },
      },
    });

    await page.goto(`/learn/giai-tich-1/${L1}`);
    await expect(page.getByRole("heading", { name: "Kiểm tra nhanh" })).toBeVisible();
    await page.getByRole("link", { name: "Làm bài" }).click();
    await expect(page).toHaveURL(new RegExp(`/quiz/${QUIZ_ID}$`));

    // Câu 1: chọn A (đúng) → thấy "Đã lưu"
    await expect(page.getByText("Câu 1/3")).toBeVisible();
    await page.getByRole("radio", { name: "0" }).check({ force: true });
    await expect(page.getByText("Đã lưu")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    // Câu 2: chọn A (sai), bỏ trống câu 3 → nộp → hộp xác nhận báo còn 1 câu
    await page.getByRole("button", { name: "Câu sau" }).click();
    await page.getByRole("radio", { name: "x", exact: true }).check({ force: true });
    await expect(page.getByText("Đã lưu")).toBeVisible();
    await page.getByRole("button", { name: "Câu sau" }).click();
    await page.getByRole("button", { name: "Nộp bài" }).first().click();
    const dialog = page.getByRole("alertdialog", { name: "Nộp bài?" });
    await expect(dialog).toContainText("Còn 1 câu chưa trả lời");
    await expect(dialog.getByRole("button", { name: "Hủy" })).toBeFocused();
    await dialog.getByRole("button", { name: "Nộp bài" }).click();

    // Kết quả
    await expect(page).toHaveURL(new RegExp(`/result/${ATTEMPT_ID}$`));
    expect(saved).toEqual({ "q-1": "A", "q-2": "A" });
    expect(submitted!.final_answers).toEqual([
      { question_id: "q-1", selected_option_id: "A" },
      { question_id: "q-2", selected_option_id: "A" },
    ]);
    await expect(page.getByText("33.3%")).toBeVisible();
    await expect(page.getByText("Chưa đạt")).toBeVisible();
    await expect(page.getByText("Câu 2 · Sai")).toBeVisible();
    await expect(page.getByText('Giải thích cho câu "Đạo hàm của x² là gì?"')).toBeVisible(); // câu sai mở sẵn giải thích
    await expect(page.getByRole("link", { name: /Làm lại \(1 lượt còn lại\)/ })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    // Quay lại bài học: thấy điểm gần nhất
    await page.getByRole("link", { name: "Về bài học" }).first().click();
    await expect(page.getByRole("link", { name: "Điểm gần nhất 33.3%" })).toBeVisible();
  });

  test("mở lại bài làm dở thì giữ đáp án đã lưu; hết lượt thì báo rõ", async ({ page }) => {
    await mockApi(page, {
      extra: {
        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz() }),
        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) => r.fulfill({ status: 200, json: attempt({ "q-1": "C" }) }),
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}/quiz/${QUIZ_ID}`);
    await expect(page.getByRole("radio", { name: "Chính hằng số đó" })).toBeChecked();
    await expect(page.getByText("Đã trả lời 1/3")).toBeVisible();

    await mockApi(page, {
      extra: {
        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz({ attempts_used: 2 }) }),
        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) =>
          r.fulfill({
            status: 409,
            json: { error: { code: "QUIZ_ATTEMPT_LIMIT", message: "Bạn đã dùng hết số lần làm bài", details: {}, request_id: null } },
          }),
      },
    });
    await page.reload();
    await expect(page.getByText("Bạn đã dùng hết số lần làm quiz này.")).toBeVisible();
  });
});
```

- [ ] **Bước 3: Kịch bản giảng viên** (`e2e/teacher-quiz.spec.ts`)

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, courseDetail, L1, mockApi, teacher } from "./mock-api";
import { bankQuestion, quiz, QUIZ_ID } from "./quiz-data";

const course = courseDetail({ status: "published", is_owner: true });

test.describe("giảng viên: câu hỏi, quiz, thống kê", () => {
  test("sinh câu hỏi bằng AI (job nền) → duyệt một câu → loại một câu rồi hoàn tác", async ({ page }) => {
    let jobPolls = 0;
    let generated = false;
    const reviews: { id: string; action: string }[] = [];
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: course }),
        [`POST /lessons/${L1}/questions/generate`]: (r) => {
          expect(r.request().postDataJSON()).toEqual({ count: 10, difficulty: { easy: 0.3, medium: 0.5, hard: 0.2 } });
          return r.fulfill({ status: 202, json: { job_id: "job-1" } });
        },
        "GET /jobs/job-1": (r) => {
          jobPolls += 1;
          const done = jobPolls >= 2;
          if (done) generated = true;
          return r.fulfill({
            json: { id: "job-1", type: "quiz_gen", status: done ? "done" : "processing", attempts: 1, error_msg: null, finished_at: null },
          });
        },
        [`GET /lessons/${L1}/questions`]: (r) =>
          r.fulfill({
            json: {
              items: generated ? [bankQuestion("c1", "pending"), bankQuestion("c2", "pending", { self_check_flag: true })] : [],
              total: generated ? 2 : 0,
              page: 1,
              size: 100,
            },
          }),
        "PATCH /questions/*": (r, url) => {
          const id = url.pathname.split("/").pop()!;
          const body = r.request().postDataJSON();
          reviews.push({ id, action: body.action });
          return r.fulfill({ json: bankQuestion(id, body.action === "approve" ? "approved" : "rejected") });
        },
      },
    });

    await page.goto(`/teach/giai-tich-1/lessons/${L1}/questions`);
    await expect(page.getByRole("tab", { name: "Chờ duyệt (0)" })).toBeVisible();
    await page.getByRole("button", { name: "Sinh câu hỏi bằng AI" }).click();
    await expect(page.getByText(/AI đang soạn/)).toBeVisible();
    await expect(page.getByText("AI đã soạn xong. Có 2 câu chờ duyệt.")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("AI tự kiểm tra thấy nghi vấn")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByRole("button", { name: "Duyệt" }).first().click();
    await expect.poll(() => reviews).toEqual([{ id: "c1", action: "approve" }]);

    // Loại câu c2 rồi bấm Hoàn tác trong 5 giây → không gửi gì
    await page.getByRole("button", { name: "Loại" }).last().click();
    await page.getByRole("button", { name: "Hoàn tác" }).click();
    await page.waitForTimeout(5500);
    expect(reviews).toEqual([{ id: "c1", action: "approve" }]);
  });

  test("tạo quiz từ câu đã duyệt → xuất bản có xác nhận", async ({ page }) => {
    let created: Record<string, unknown> | null = null;
    let published = false;
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: course }),
        [`GET /lessons/${L1}/questions`]: (r) =>
          r.fulfill({ json: { items: [bankQuestion("c1", "approved"), bankQuestion("c2", "edited"), bankQuestion("c3", "pending")], total: 3, page: 1, size: 100 } }),
        "GET /quizzes": (r) =>
          r.fulfill({
            json: created
              ? { items: [quiz({ status: published ? "published" : "draft", question_count: 2, attempts_used: null })], total: 1, page: 1, size: 50 }
              : { items: [], total: 0, page: 1, size: 50 },
          }),
        "POST /quizzes": (r) => {
          created = r.request().postDataJSON();
          return r.fulfill({ status: 201, json: quiz({ status: "draft", question_count: 2 }) });
        },
        [`POST /quizzes/${QUIZ_ID}/publish`]: (r) => {
          published = true;
          return r.fulfill({ json: quiz() });
        },
      },
    });

    await page.goto(`/teach/giai-tich-1/lessons/${L1}/quizzes`);
    await page.getByRole("button", { name: "Tạo quiz" }).click();
    const dialog = page.getByRole("dialog", { name: "Tạo quiz" });
    await expect(dialog.getByText("Câu hỏi đã duyệt (0/2 được chọn)")).toBeVisible(); // câu chờ duyệt không được chọn
    await dialog.getByLabel("Tiêu đề").fill("Kiểm tra đạo hàm cơ bản");
    for (const cb of await dialog.getByRole("checkbox").all()) await cb.check();
    await dialog.getByRole("button", { name: "Tạo quiz" }).click();
    await expect.poll(() => created).toMatchObject({ lesson_id: L1, title: "Kiểm tra đạo hàm cơ bản", question_ids: ["c1", "c2"] });

    await page.getByRole("button", { name: "Xuất bản" }).click();
    const confirm = page.getByRole("alertdialog");
    await expect(confirm.getByRole("button", { name: "Hủy" })).toBeFocused();
    await confirm.getByRole("button", { name: "Xuất bản" }).click();
    await expect(page.getByText("Đã xuất bản", { exact: true })).toBeVisible();
    await expectAccessible(page);
  });

  test("trang thống kê hiện số liệu khóa, tỉ lệ hoàn thành và quiz", async ({ page }) => {
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: course }),
        [`GET /courses/${COURSE_ID}/analytics`]: (r) =>
          r.fulfill({
            json: {
              course_id: COURSE_ID,
              enrollments: 12,
              completed_enrollments: 3,
              lessons: [
                { lesson_id: L1, title: "Định nghĩa đạo hàm", section_title: "Đạo hàm", done_count: 9, completion_rate: 0.75 },
              ],
              quizzes: [
                { quiz_id: QUIZ_ID, lesson_id: L1, title: "Kiểm tra đạo hàm cơ bản", status: "published", attempts: 10, students: 8, avg_score: 71.25, pass_rate: 0.625 },
              ],
              tutor: { sessions: 20, questions: 57, refused_answers: 4 },
            },
          }),
      },
    });
    await page.goto("/teach/giai-tich-1/analytics");
    await expect(page.getByRole("heading", { name: "Thống kê khóa học" })).toBeVisible();
    await expect(page.getByText("9/12 · 75%")).toBeVisible();
    await expect(page.getByText("71.3%")).toBeVisible();
    await expect(page.getByText("63%")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });
});
```

- [ ] **Bước 4: Chạy**

Run: `npm run e2e`
Expected: `28 passed` (18 test cũ, 10 test mới).

Kịch bản "Hoàn tác" chờ 5,5 giây có chủ đích, để chứng minh không có request loại câu nào được gửi đi.

Nếu axe báo `color-contrast` ở dòng "Đáp án đúng", kiểm tra lại rằng chữ dùng màu chữ thường, chỉ icon mang màu `text-success` (xem §0.3).

- [ ] **Bước 5: Commit và push**

```bash
git add frontend/e2e && git commit -m "test(web): E2E for quiz taking, question review and analytics"
git push
```

Expected: CI xanh, kể cả job `frontend` (gồm cả E2E).

---

## Task 12: Kiểm tra với backend thật và cập nhật spec

Task này **người dùng tự làm**. Chạy backend với `LLM_PROVIDER=fake` cho nhanh. Riêng bước sinh câu hỏi bằng AI có thể bật Gemini nếu còn quota.

- [ ] Đăng nhập giảng viên → mở một bài đã có PDF ở trạng thái "Sẵn sàng" → tab **Câu hỏi** → **Sinh câu hỏi bằng AI** (5 câu). Thấy dòng "AI đang soạn…", trang vẫn thao tác được. Khi xong có toast báo số câu chờ duyệt.
- [ ] Duyệt 3 câu. Sửa 1 câu, thử xóa trắng một lựa chọn để thấy lỗi 422 hiện tại chỗ, sửa lại rồi lưu. Loại 1 câu rồi bấm Hoàn tác, sau đó loại hẳn.
- [ ] Tab **Quiz** → **Tạo quiz** với 3–4 câu đã duyệt, đặt 2 lượt và điểm đạt 60% → **Xuất bản**.
- [ ] Đăng nhập học viên → mở bài → mục "Kiểm tra nhanh" → **Làm bài** → chọn đáp án, thấy "Đã lưu" → tải lại trang (F5), đáp án vẫn còn → nộp với 1 câu bỏ trống, hộp xác nhận báo "Còn 1 câu…" → xem kết quả, câu sai có mở sẵn giải thích → **Làm lại** → nộp lần 2 → quay lại bài học, thấy "Đã hết lượt" và "Điểm gần nhất".
- [ ] Giảng viên → trình soạn khóa → **Thống kê**: thấy 1 học viên, tỉ lệ hoàn thành bài, quiz có 2 bài nộp với điểm TB, tỉ lệ đạt, số câu hỏi AI Tutor.
- [ ] Thử xóa quiz đã có bài làm: hộp thoại vẫn mở và hiện thông báo 409 "Quiz đã xuất bản, không xóa được".
- [ ] Chuyển DevTools sang 375px: lưới câu hỏi vừa màn hình, bảng thống kê cuộn ngang được, không có cuộn ngang cả trang.
- [ ] Cập nhật `docs/specs/2026-09-29-lms-ai-design.md`:
  - Đánh dấu xong các mục frontend của A5–A8 trong bảng tiến độ, và **mốc M1** (bản chạy được đầu tiên, xong tầng A).
  - Thêm vào nhật ký quyết định:

```markdown
| 2026-10-06 | FE-2: tự lưu đáp án bằng hàng đợi tuần tự, nộp bài luôn kèm final_answers; loại câu hỏi có Hoàn tác 5 giây (gửi trễ thay vì gọi API khôi phục); bài làm gần nhất lưu ở localStorage vì chưa có API danh sách bài làm (để B1 bổ sung `GET /quizzes/{id}/attempts/me`). |
```

```bash
git add docs && git commit -m "docs: FE-2 done, milestone M1 reached"
```

---

## Phụ lục: Ánh xạ yêu cầu → task

| Yêu cầu | Task |
|---|---|
| Quiz: Bắt đầu, chọn đáp án tự lưu ("Đã lưu"), Câu trước/sau, Nộp bài có xác nhận số câu chưa trả lời (design §5.3) | 1, 3, 4 |
| Kết quả: xem giải thích câu sai, Làm lại (ẩn khi hết lượt) | 5 |
| Quiz trong trang bài học | 6 |
| Sinh câu hỏi bằng AI: "AI đang soạn… (≈1 phút)", không khóa trang, toast kèm số câu chờ duyệt | 8 |
| Duyệt / Sửa / Loại (Hoàn tác 5 giây) | 8 |
| Tạo / Xuất bản (có xác nhận) / Xóa (trong menu ⋯, có xác nhận) quiz | 9 |
| Dashboard giảng viên (A8) | 10 |
| Không nhắc nghỉ mắt khi làm quiz có giờ (design §8) | 4 |
| Responsive 375/1280, WCAG AA | 11 |

**Còn lại cho tầng B:**

- **B1:** quiz có giờ (`deadline_at`), cron chốt bài khi hết giờ, API danh sách bài làm, xáo trộn câu và lựa chọn.
- **B3:** AI giải thích câu học viên làm sai.
- **B7:** câu hay sai, chủ đề yếu.
- **B8:** trang admin.
