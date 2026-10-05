import { describe, expect, it } from "vitest";
import { readSse } from "./sse";

function streamOf(chunks: string[]) {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((s) => c.enqueue(enc.encode(s)));
      c.close();
    },
  });
}

async function collect(chunks: string[]) {
  const out = [];
  for await (const e of readSse(streamOf(chunks))) out.push(e);
  return out;
}

describe("readSse", () => {
  it("tách các event theo dòng trống", async () => {
    const events = await collect(['event: token\ndata: {"text":"Xin"}\n\nevent: token\ndata: {"text":" chào"}\n\n']);
    expect(events).toEqual([
      { event: "token", data: '{"text":"Xin"}' },
      { event: "token", data: '{"text":" chào"}' },
    ]);
  });

  it("ghép event bị cắt giữa 2 chunk mạng, kể cả cắt giữa ký tự UTF-8", async () => {
    const full = 'event: done\ndata: {"content":"Đạo hàm"}\n\n';
    const bytes = new TextEncoder().encode(full);
    // cắt ở byte 31: "Đ" chiếm byte 30–31 (0xC4 0x90), nên chunk đầu dừng giữa ký tự
    const s = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, 31));
        c.enqueue(bytes.slice(31));
        c.close();
      },
    });
    const out = [];
    for await (const e of readSse(s)) out.push(e);
    expect(out).toEqual([{ event: "done", data: '{"content":"Đạo hàm"}' }]);
  });

  it("chấp nhận \r\n và bỏ qua dòng comment", async () => {
    const events = await collect([": ping\r\n\r\nevent: error\r\ndata: {\"code\":\"AI_UNAVAILABLE\"}\r\n\r\n"]);
    expect(events).toEqual([{ event: "error", data: '{"code":"AI_UNAVAILABLE"}' }]);
  });

  it("đọc được event cuối dù thiếu dòng trống kết thúc", async () => {
    expect(await collect(['event: done\ndata: {"a":1}'])).toEqual([{ event: "done", data: '{"a":1}' }]);
  });
});
