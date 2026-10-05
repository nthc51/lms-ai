"use client";

import * as React from "react";

export type AutosaveState =
  | { status: "idle" }
  | { status: "dirty" }
  | { status: "saving" }
  | { status: "saved"; at: Date }
  | { status: "error"; message: string };

/**
 * Tự lưu sau khi ngừng gõ `delay` ms. Các lần lưu chạy TUẦN TỰ: nếu đang lưu mà có thay đổi mới,
 * đợi lần lưu hiện tại xong rồi lưu bản mới nhất (không bao giờ ghi đè bản mới bằng bản cũ).
 * `flush()` lưu ngay (nút "Lưu", rời trang).
 */
export function useAutosave<T>(value: T, save: (v: T) => Promise<unknown>, { delay = 1000, enabled = true } = {}) {
  const [state, setState] = React.useState<AutosaveState>({ status: "idle" });
  const latest = React.useRef(value);
  const saved = React.useRef(value);
  const saveRef = React.useRef(save);
  const running = React.useRef<Promise<void> | null>(null);
  const timer = React.useRef<number | undefined>(undefined);

  React.useEffect(() => {
    saveRef.current = save;
  });

  // Một vòng lặp duy nhất: lưu bản mới nhất cho tới khi khớp với bản đã lưu, rồi dừng.
  const run = React.useCallback((): Promise<void> => {
    if (running.current) return running.current; // vòng đang chạy sẽ tự lấy bản mới nhất
    running.current = (async () => {
      while (!Object.is(latest.current, saved.current)) {
        const v = latest.current;
        setState({ status: "saving" });
        try {
          await saveRef.current(v);
          saved.current = v;
        } catch (err) {
          setState({ status: "error", message: err instanceof Error ? err.message : "Không lưu được" });
          return;
        }
      }
      setState({ status: "saved", at: new Date() });
    })().finally(() => {
      running.current = null;
    });
    return running.current;
  }, []);

  React.useEffect(() => {
    latest.current = value;
    if (!enabled || Object.is(value, saved.current)) return;
    setState({ status: "dirty" });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void run(), delay);
    return () => window.clearTimeout(timer.current);
  }, [value, delay, enabled, run]);

  /** Đặt lại mốc "đã lưu" khi tải dữ liệu mới từ server (đổi bài). */
  const reset = React.useCallback((v: T) => {
    latest.current = v;
    saved.current = v;
    setState({ status: "idle" });
  }, []);

  const flush = React.useCallback(() => {
    window.clearTimeout(timer.current);
    return run();
  }, [run]);

  return { state, flush, reset };
}

export function autosaveLabel(s: AutosaveState) {
  switch (s.status) {
    case "dirty":
      return "Chưa lưu";
    case "saving":
      return "Đang lưu…";
    case "saved":
      return `Đã lưu lúc ${s.at.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
    case "error":
      return `Lưu thất bại: ${s.message}`;
    default:
      return "";
  }
}
