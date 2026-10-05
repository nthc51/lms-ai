import { describe, expect, it } from "vitest";
import { validateFile } from "./upload";

const file = (type: string, size: number) => {
  const f = new File(["x"], "a", { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

describe("validateFile", () => {
  it("nhận PDF đúng loại và dưới 50MB", () => {
    expect(validateFile("pdf", file("application/pdf", 1024))).toBeNull();
  });
  it("từ chối sai loại", () => {
    expect(validateFile("pdf", file("image/png", 10))).toMatch(/Chỉ nhận file PDF/);
  });
  it("từ chối file quá lớn", () => {
    expect(validateFile("video", file("video/mp4", 600 * 1024 * 1024))).toMatch(/quá lớn/);
  });
});
