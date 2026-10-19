import { describe, expect, it } from "vitest";
import { timeAgo } from "./format";

describe("timeAgo", () => {
  const now = new Date(2026, 9, 19, 12, 0, 0).getTime();
  const ago = (sec: number) => new Date(now - sec * 1000).toISOString();

  it("đổi khoảng thời gian sang chữ tiếng Việt", () => {
    expect(timeAgo(ago(30), now)).toBe("vừa xong");
    expect(timeAgo(ago(5 * 60), now)).toBe("5 phút trước");
    expect(timeAgo(ago(3 * 3600), now)).toBe("3 giờ trước");
    expect(timeAgo(ago(2 * 86400), now)).toBe("2 ngày trước");
  });

  it("quá 30 ngày thì ghi ngày/tháng/năm; thời điểm trong tương lai coi như vừa xong", () => {
    expect(timeAgo(new Date(2026, 7, 2, 9, 0).toISOString(), now)).toBe("02/08/2026");
    expect(timeAgo(ago(-120), now)).toBe("vừa xong");
  });
});
