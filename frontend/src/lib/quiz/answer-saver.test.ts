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
