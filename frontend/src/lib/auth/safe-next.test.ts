import { describe, expect, it } from "vitest";
import { safeNext } from "./safe-next";

describe("safeNext", () => {
  it("giữ đường dẫn nội bộ", () => expect(safeNext("/learn/a/b")).toBe("/learn/a/b"));
  it("chặn URL ngoài và //", () => {
    expect(safeNext("https://evil.com")).toBe("/");
    expect(safeNext("//evil.com")).toBe("/");
    expect(safeNext("/\\evil.com")).toBe("/");
  });
  it("rỗng thì dùng fallback", () => expect(safeNext(null, "/my")).toBe("/my"));
});
