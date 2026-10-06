import { describe, expect, it } from "vitest";
import { questionErrorText } from "./question-card";

describe("questionErrorText", () => {
  it("đổi lỗi Pydantic thường gặp sang tiếng Việt", () => {
    expect(questionErrorText({ loc: ["stem"], msg: "String should have at least 10 characters", type: "string_too_short" })).toBe(
      "Đề bài phải có ít nhất 10 ký tự",
    );
    expect(questionErrorText({ loc: ["options", 1, "text"], msg: "String should have at least 1 character", type: "string_too_short" })).toBe(
      "Lựa chọn không được để trống",
    );
    expect(questionErrorText({ loc: ["body", "stem"], msg: "String should have at most 1000 characters", type: "string_too_long" })).toBe(
      "Đề bài tối đa 1000 ký tự",
    );
    expect(questionErrorText({ loc: ["difficulty"], msg: "Field required", type: "missing" })).toBe("Thiếu thông tin bắt buộc");
    expect(questionErrorText({ loc: [], msg: "Value error, Mã lựa chọn bị trùng", type: "value_error" })).toBe("Mã lựa chọn bị trùng");
  });
});
