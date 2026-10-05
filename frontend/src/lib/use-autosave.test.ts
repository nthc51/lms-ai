import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAutosave } from "./use-autosave";

describe("useAutosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("lưu một lần sau khi ngừng gõ 1 giây", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { rerender, result } = renderHook(({ v }) => useAutosave(v, save), { initialProps: { v: "a" } });
    rerender({ v: "ab" });
    rerender({ v: "abc" });
    expect(result.current.state.status).toBe("dirty");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("abc");
    expect(result.current.state.status).toBe("saved");
  });

  it("đang lưu mà gõ tiếp: không gửi song song, lưu bản mới nhất sau", async () => {
    let resolveFirst!: () => void;
    const calls: string[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const save = vi.fn((v: string) => {
      calls.push(v);
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      return new Promise<void>((r) => {
        const done = () => {
          inFlight--;
          r();
        };
        if (calls.length === 1) resolveFirst = done;
        else done();
      });
    });
    const { rerender } = renderHook(({ v }) => useAutosave(v, save), { initialProps: { v: "x" } });
    rerender({ v: "x1" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    rerender({ v: "x12" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(calls).toEqual(["x1"]); // lần 2 đang đợi lần 1
    await act(async () => {
      resolveFirst();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(calls).toEqual(["x1", "x12"]);
    expect(maxInFlight).toBe(1);
  });

  it("lỗi thì báo trạng thái error", async () => {
    const save = vi.fn().mockRejectedValue(new Error("Mất mạng"));
    const { rerender, result } = renderHook(({ v }) => useAutosave(v, save), { initialProps: { v: 1 } });
    rerender({ v: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.state).toEqual({ status: "error", message: "Mất mạng" });
  });
});
