import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { forgotErrorMessage, isDeadResetLink } from "./password-reset";

describe("password reset helpers", () => {
  it("429: báo số phút phải chờ", () => {
    expect(forgotErrorMessage(new ApiError(429, "RATE_LIMITED", "x", null, {}, 1500))).toContain("khoảng 25 phút");
  });
  it("chỉ link hỏng / hết hạn mới bắt xin link mới", () => {
    expect(isDeadResetLink(new ApiError(400, "INVALID_TOKEN", "x", null, {}, null))).toBe(true);
    expect(isDeadResetLink(new ApiError(400, "TOKEN_EXPIRED", "x", null, {}, null))).toBe(true);
    expect(isDeadResetLink(new ApiError(422, "VALIDATION_ERROR", "x", null, {}, null))).toBe(false);
    expect(isDeadResetLink(new Error("mất mạng"))).toBe(false);
  });
});
