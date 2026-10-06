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
