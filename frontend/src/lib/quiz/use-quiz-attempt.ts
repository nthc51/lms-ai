"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { ApiError } from "@/lib/api/errors";
import { AnswerSaver, type SaveState } from "./answer-saver";
import { lastAttempt } from "./attempt-store";
import { quizKeys, saveAnswer, startAttempt, submitAttempt } from "./queries";
import type { AttemptResult } from "./types";

/** Bài đã nộp ở tab/thiết bị khác: lưu hay nộp tiếp đều vô ích, giao diện nên chuyển sang trang kết quả. */
const isAttemptClosed = (e: unknown) => e instanceof ApiError && e.code === "ATTEMPT_CLOSED";

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
  // true khi server báo ATTEMPT_CLOSED: câu lưu lỗi KHÔNG còn "sẽ gửi khi nộp"
  const [closed, setClosed] = React.useState(false);
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
          (q, o) =>
            saveAnswer(attemptId, q, o).catch((e: unknown) => {
              if (isAttemptClosed(e)) setClosed(true);
              throw e;
            }),
          (q, st) => setPickedStates((prev) => ({ ...prev, [q]: st })),
        ),
      };
    }
    return saverRef.current.saver;
  }, []);

  const select = React.useCallback(
    (questionId: string, optionId: string) => {
      if (!a || closed) return;
      setPicked((prev) => ({ ...prev, [questionId]: optionId }));
      saverFor(a.id).enqueue(questionId, optionId);
    },
    [a, closed, saverFor],
  );

  const submit = React.useCallback(async (): Promise<AttemptResult> => {
    if (!a) throw new Error("Bài làm chưa sẵn sàng");
    let result: AttemptResult;
    try {
      // đã đóng thì không gửi lại các câu lỗi (chắc chắn 409)
      if (!closed) await saverFor(a.id).flush(); // đợi các lần lưu đang chạy; câu lưu lỗi vẫn được gửi trong final_answers
      result = await submitAttempt(a.id, answers);
    } catch (e) {
      if (isAttemptClosed(e)) setClosed(true); // nơi gọi quyết định (Task 4 chuyển sang trang kết quả)
      throw e;
    }
    lastAttempt.set(quizId, { attemptId: a.id, status: result.status, score: result.score, passed: result.passed });
    qc.setQueryData(quizKeys.result(a.id), result);
    qc.invalidateQueries({ queryKey: quizKeys.quiz(quizId) });
    qc.invalidateQueries({ queryKey: ["lesson-quizzes"] });
    return result;
  }, [a, answers, closed, quizId, qc, saverFor]);

  return { attempt, attemptId: a?.id ?? null, closed, answers, saveStates, select, submit };
}
