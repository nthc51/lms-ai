import { describe, expect, it } from "vitest";
import { lastLesson, readerSize, scrollPosition } from "./storage";

describe("study storage", () => {
  it("cỡ chữ mặc định 17 và luôn bị kẹp trong 15–21", () => {
    expect(readerSize.get()).toBe(17);
    readerSize.set(30);
    expect(readerSize.get()).toBe(21);
    readerSize.set(2);
    expect(readerSize.get()).toBe(15);
  });

  it("nhớ bài gần nhất theo từng khóa", () => {
    lastLesson.set("c1", "l9");
    expect(lastLesson.get("c1")).toBe("l9");
    expect(lastLesson.get("c2")).toBeNull();
  });

  it("dữ liệu hỏng thì trả giá trị mặc định thay vì ném lỗi", () => {
    localStorage.setItem("lms:scroll:l1", "{hỏng");
    expect(scrollPosition.get("l1")).toBe(0);
  });
});
