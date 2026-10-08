import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { resendErrorMessage } from "./email-verification";

describe("resendErrorMessage", () => {
  it("429: báo số phút phải chờ (làm tròn lên, ít nhất 1 phút)", () => {
    const err = (s: number | null) => new ApiError(429, "RATE_LIMITED", "x", null, {}, s);
    expect(resendErrorMessage(err(1500))).toContain("khoảng 25 phút");
    expect(resendErrorMessage(err(10))).toContain("khoảng 1 phút");
    expect(resendErrorMessage(err(null))).toContain("khoảng 1 phút");
  });
  it("lỗi khác: giữ thông báo của lỗi", () => {
    expect(resendErrorMessage(new Error("Mất mạng"))).toBe("Mất mạng");
  });
});
