/**
 * Nội dung mẫu cho phần "Thử hỏi" ở trang chủ: 4 câu hỏi về một bài Kỹ thuật truyền thông, trả lời theo
 * đúng cách AI Tutor hiển thị (đoạn văn có [n], danh sách nguồn có số trang, đoạn tài liệu được dùng).
 * Đây là ví dụ cố định để khách xem trước, không gọi API. Thay bằng nội dung khóa học thật nếu muốn.
 * Chuỗi có thẻ <sub>/<span class="hl"> do code này tự viết (không phải dữ liệu người dùng).
 */
export type SampleKey = "am" | "shannon" | "noise" | "ticket";

export type SampleAnswer = {
  label: string;
  question: string;
  paragraphs?: string[];
  sources?: { title: string; page: number }[];
  excerpt?: { page: number; html: string };
  refusal?: string;
  followups: string[];
};

export const SAMPLES: Record<SampleKey, SampleAnswer> = {
  am: {
    label: "Điều chế AM",
    question: "Điều chế AM là gì, băng thông bao nhiêu?",
    paragraphs: [
      "Điều chế biên độ (AM) thay đổi biên độ của sóng mang theo tín hiệu tin tức, còn tần số và pha của sóng mang giữ nguyên [1].",
      "Phổ tín hiệu AM gồm sóng mang và hai dải biên đối xứng quanh tần số sóng mang, nên băng thông bằng hai lần tần số cao nhất của tín hiệu tin tức [2].",
    ],
    sources: [
      { title: "Chương 3 · Điều chế biên độ", page: 47 },
      { title: "Chương 3 · Phổ của tín hiệu AM", page: 49 },
    ],
    excerpt: {
      page: 49,
      html: 'Phổ của tín hiệu AM gồm thành phần sóng mang tại f<sub>c</sub> và hai dải biên. <span class="hl">Băng thông của tín hiệu AM bằng 2·f<sub>max</sub></span>, trong đó f<sub>max</sub> là tần số cao nhất của tín hiệu tin tức.',
    },
    followups: ["So sánh AM với FM?", "Chỉ số điều chế là gì?"],
  },
  shannon: {
    label: "Dung lượng kênh",
    question: "Dung lượng kênh phụ thuộc vào những gì?",
    paragraphs: [
      "Theo định lý Shannon–Hartley, dung lượng kênh C = B·log<sub>2</sub>(1 + S/N): tăng tỉ lệ thuận với băng thông B và tăng theo log của tỉ số tín hiệu trên nhiễu [1].",
      "Ví dụ trong bài: kênh thoại rộng 3,1 kHz với S/N = 30 dB có dung lượng khoảng 30,9 kbit/s [2].",
    ],
    sources: [
      { title: "Chương 2 · Dung lượng kênh", page: 31 },
      { title: "Chương 2 · Ví dụ kênh thoại", page: 32 },
    ],
    excerpt: {
      page: 31,
      html: 'Với kênh có nhiễu Gauss trắng cộng, <span class="hl">dung lượng kênh C = B·log<sub>2</sub>(1 + S/N)</span> (bit/s), trong đó B là băng thông và S/N là tỉ số công suất tín hiệu trên nhiễu.',
    },
    followups: ["30 dB đổi ra S/N là bao nhiêu?", "Giới hạn Shannon là gì?"],
  },
  noise: {
    label: "Nhiễu trắng",
    question: "Nhiễu trắng là gì?",
    paragraphs: [
      "Nhiễu trắng có mật độ phổ công suất như nhau ở mọi tần số, thường viết là N<sub>0</sub>/2 [1].",
      "Nhiễu nhiệt trong máy thu được mô hình hóa là nhiễu Gauss trắng cộng (AWGN) khi phân tích hệ thống [2].",
    ],
    sources: [
      { title: "Chương 2 · Các loại nhiễu", page: 22 },
      { title: "Chương 2 · Mô hình kênh AWGN", page: 24 },
    ],
    excerpt: {
      page: 22,
      html: '<span class="hl">Nhiễu trắng là nhiễu có mật độ phổ công suất không đổi trên toàn bộ dải tần</span>, ký hiệu N<sub>0</sub>/2 (W/Hz) với phổ hai phía.',
    },
    followups: ["Nhiễu nhiệt phụ thuộc nhiệt độ thế nào?", "AWGN là gì?"],
  },
  ticket: {
    label: "Giá vé tàu",
    question: "Giá vé tàu Hà Nội – Sài Gòn bao nhiêu?",
    refusal:
      "Tài liệu của khóa Kỹ thuật truyền thông không nói đến giá vé tàu, nên mình không trả lời được câu này. Bạn có thể hỏi về nội dung trong bài, ví dụ điều chế, nhiễu hay dung lượng kênh.",
    followups: ["Điều chế FM khác AM thế nào?", "Tỉ số S/N là gì?"],
  },
};

export const SAMPLE_KEYS = Object.keys(SAMPLES) as SampleKey[];
