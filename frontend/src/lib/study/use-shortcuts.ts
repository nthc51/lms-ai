"use client";

import * as React from "react";

export type ShortcutMap = Record<string, (e: KeyboardEvent) => void>;

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

/**
 * Phím tắt một phím (design-system §8): "/", "f", "ArrowLeft", "ArrowRight", "Escape", "?".
 * Bỏ qua khi đang gõ trong ô nhập (trừ Escape) hoặc khi có Ctrl/Alt/Meta.
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
      if (e.key !== "Escape" && isTyping(e.target)) return;
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
