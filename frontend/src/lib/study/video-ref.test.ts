import { describe, expect, it, vi } from "vitest";
import { attachVideoRef } from "./video-ref";

describe("attachVideoRef", () => {
  it("gán videoRef và gọi bind", () => {
    const ref = { current: null as HTMLVideoElement | null };
    const bind = vi.fn();
    const el = document.createElement("video");
    attachVideoRef(ref, bind, el);
    expect(ref.current).toBe(el);
    expect(bind).toHaveBeenCalledWith(el);
  });

  it("cleanup gọi cleanup của bind và xoá videoRef", () => {
    const ref = { current: null as HTMLVideoElement | null };
    const inner = vi.fn();
    const el = document.createElement("video");
    const cleanup = attachVideoRef(ref, () => inner, el);
    cleanup();
    expect(inner).toHaveBeenCalled();
    expect(ref.current).toBeNull();
  });

  it("không xoá videoRef nếu đã trỏ sang video mới", () => {
    const ref = { current: null as HTMLVideoElement | null };
    const a = document.createElement("video");
    const b = document.createElement("video");
    const cleanupA = attachVideoRef(ref, () => undefined, a);
    attachVideoRef(ref, () => undefined, b);
    cleanupA();
    expect(ref.current).toBe(b);
  });
});
