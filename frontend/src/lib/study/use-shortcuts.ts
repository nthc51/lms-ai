"use client";

import * as React from "react";

export type ShortcutMap = Record<string, (e: KeyboardEvent) => void>;

const WIDGET_SELECTOR =
  '[role="dialog"],[role="alertdialog"],[role="slider"],[role="tab"],[role="menu"],[role="listbox"]';

/** Ô nhập: bỏ qua mọi phím trừ Escape. */
function isTyping(el: HTMLElement) {
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

/** Video/audio đang focus: phím mũi tên là của trình phát (tua), Escape vẫn cho qua. */
function isMedia(el: HTMLElement) {
  return el.tagName === "VIDEO" || el.tagName === "AUDIO";
}

/** Hộp thoại, thanh trượt, tab, menu, listbox tự xử lý phím của chúng (kể cả Escape). */
function isInsideWidget(el: HTMLElement) {
  return typeof el.closest === "function" && el.closest(WIDGET_SELECTOR) !== null;
}

function shouldIgnore(e: KeyboardEvent) {
  const el = e.target as HTMLElement | null;
  if (!el || el === (window as unknown)) return false;
  if (isInsideWidget(el)) return true;
  if (e.key === "Escape") return false;
  return isTyping(el) || isMedia(el);
}

/**
 * Phím tắt một phím (design-system §8): "/", "f", "ArrowLeft", "ArrowRight", "Escape", "?".
 * Bỏ qua khi đang gõ trong ô nhập (trừ Escape), khi focus ở video/audio (trừ Escape),
 * khi ở trong dialog/slider/tab/menu/listbox, hoặc khi có Ctrl/Alt/Meta.
 */
export function useShortcuts(map: ShortcutMap, enabled = true) {
  const ref = React.useRef(map);
  React.useEffect(() => {
    ref.current = map;
  });
  React.useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey || e.defaultPrevented) return;
      if (shouldIgnore(e)) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const handler = ref.current[key];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
