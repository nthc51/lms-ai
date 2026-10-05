"use client";

import * as React from "react";
import { breakPrefs } from "./storage";

export const BREAK_AFTER_MS = 45 * 60_000;
export const SNOOZE_MS = 15 * 60_000;
const IDLE_RESET_MS = 5 * 60_000; // rời máy > 5 phút coi như đã nghỉ

/**
 * Nhắc nghỉ mắt sau 45 phút học liên tục (design-system §8).
 * Chỉ đếm khi tab đang hiển thị; tạm dừng khi `paused` (vd. đang làm quiz có giờ).
 */
export function useBreakReminder({ paused = false }: { paused?: boolean } = {}) {
  const [due, setDue] = React.useState(false);
  // hook chỉ chạy trong trang client-only (sau RequireAuth) nên đọc localStorage lúc khởi tạo được
  const [enabled, setEnabled] = React.useState(() => breakPrefs.get().enabled);
  const activeMs = React.useRef(0);
  const lastTick = React.useRef(0);
  const lastActivity = React.useRef(0);

  React.useEffect(() => {
    lastActivity.current = Date.now();
    const mark = () => {
      lastActivity.current = Date.now();
    };
    const events = ["pointerdown", "keydown", "scroll", "wheel"] as const;
    events.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    return () => events.forEach((e) => window.removeEventListener(e, mark));
  }, []);

  React.useEffect(() => {
    if (!enabled || paused) return;
    lastTick.current = Date.now();
    const id = window.setInterval(() => {
      const now = Date.now();
      const delta = now - lastTick.current;
      lastTick.current = now;
      if (document.visibilityState !== "visible") return;
      if (now - lastActivity.current > IDLE_RESET_MS) {
        activeMs.current = 0;
        return;
      }
      activeMs.current += delta;
      if (activeMs.current >= BREAK_AFTER_MS && now >= breakPrefs.get().snoozeUntil) setDue(true);
    }, 30_000);
    return () => window.clearInterval(id);
  }, [enabled, paused]);

  const done = React.useCallback(() => {
    activeMs.current = 0;
    setDue(false);
  }, []);
  const snooze = React.useCallback(() => {
    breakPrefs.set({ ...breakPrefs.get(), snoozeUntil: Date.now() + SNOOZE_MS });
    activeMs.current = 0;
    setDue(false);
  }, []);
  const disable = React.useCallback(() => {
    breakPrefs.set({ ...breakPrefs.get(), enabled: false });
    setEnabled(false);
    setDue(false);
  }, []);

  return { due: due && enabled && !paused, done, snooze, disable };
}
