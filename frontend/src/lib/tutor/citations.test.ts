import { describe, expect, it } from "vitest";
import { formatTimestamp, linkCitations } from "./citations";

describe("linkCitations", () => {
  it("đổi [n] hợp lệ thành link, giữ nguyên số không có trong nguồn", () => {
    expect(linkCitations("Theo [1] và [3].", new Set([1, 2]))).toBe("Theo [1](#cite-1) và [3].");
  });
  it("không đụng vào code", () => {
    expect(linkCitations("`a[1]` và [1]", new Set([1]))).toBe("`a[1]` và [1](#cite-1)");
  });
  it("không đổi link markdown có sẵn", () => {
    expect(linkCitations("[1](http://x)", new Set([1]))).toBe("[1](http://x)");
  });
});

describe("formatTimestamp", () => {
  it("phút:giây và giờ:phút:giây", () => {
    expect(formatTimestamp(75.4)).toBe("1:15");
    expect(formatTimestamp(3725)).toBe("1:02:05");
  });
});
