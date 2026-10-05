import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { breakPrefs } from "./storage";
import { useBreakReminder } from "./use-break-reminder";

function study(minutes: number) {
  // mỗi 30 giây có một tương tác, giống người đang đọc và cuộn
  for (let i = 0; i < minutes * 2; i++) {
    act(() => {
      window.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(30_000);
    });
  }
}

describe("useBreakReminder", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("nhắc sau 45 phút học liên tục", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(44);
    expect(result.current.due).toBe(false);
    study(1.5);
    expect(result.current.due).toBe(true);
  });

  it("không nhắc khi đang làm quiz (paused)", () => {
    const { result } = renderHook(() => useBreakReminder({ paused: true }));
    study(60);
    expect(result.current.due).toBe(false);
  });

  it("rời máy hơn 5 phút thì đếm lại từ đầu", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(40);
    act(() => {
      vi.advanceTimersByTime(6 * 60_000); // không có tương tác
    });
    study(10);
    expect(result.current.due).toBe(false);
  });

  it("Tắt nhắc thì lưu lại và không nhắc nữa", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(46);
    act(() => result.current.disable());
    expect(result.current.due).toBe(false);
    expect(breakPrefs.get().enabled).toBe(false);
  });

  it("máy ngủ lâu rồi có tương tác thì đếm lại, không nhắc ngay", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(10);
    act(() => {
      vi.setSystemTime(Date.now() + 60 * 60_000); // máy ngủ 1 giờ
      window.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(30_000);
    });
    expect(result.current.due).toBe(false);
    study(40);
    expect(result.current.due).toBe(false);
  });

  it("mỗi nhịp chỉ cộng tối đa một chu kỳ khi đồng hồ nhảy ngắn", () => {
    const { result } = renderHook(() => useBreakReminder());
    study(40);
    act(() => {
      vi.setSystemTime(Date.now() + 4 * 60_000); // nhảy 4 phút (< 5 phút)
      window.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(30_000);
    });
    study(3);
    expect(result.current.due).toBe(false); // cộng dồn 4 phút sẽ vượt 45 phút
  });

  it("ẩn tab hơn 5 phút rồi quay lại thì đếm lại từ đầu", () => {
    const state = vi.spyOn(document, "visibilityState", "get");
    const { result } = renderHook(() => useBreakReminder());
    study(40);
    state.mockReturnValue("hidden");
    study(6); // vẫn có tương tác nhưng tab đang ẩn
    state.mockReturnValue("visible");
    study(10);
    state.mockRestore();
    expect(result.current.due).toBe(false);
  });
});
