# Design System — LMS-AI

- **Áp dụng cho:** frontend Next.js + Tailwind + shadcn/ui
- **Nguồn:** `ui-ux-pro-max` (font, quy tắc UX về nút và phản hồi), cộng với điều chỉnh riêng cho việc học nhiều giờ
- **Ngày:** 2026-10-01

---

## 1. Nguyên tắc: dịu mắt khi học lâu

1. **Không dùng trắng tuyệt đối (#FFF) và đen tuyệt đối (#000) làm nền hay chữ.** Nền sáng là màu giấy ấm, nền tối là xám than. Chữ không dùng đen hay trắng thuần.
2. **Tương phản vừa đủ, không gắt.** Chữ nội dung đạt 10.9–14.4:1 (trên chuẩn AAA 7:1), nhưng không chạm mức 21:1 như đen trên trắng. Chữ phụ đạt ≥ 5.4:1.
3. **Màu nhấn dùng tiết kiệm.** Màu chính (xanh lục lam đậm) chỉ dùng cho **một hành động chính** trên mỗi màn hình và cho trạng thái đang chọn. Phần còn lại là trung tính.
4. **Chữ đọc lớn, dòng ngắn.** Nội dung bài 17px (chỉnh được 15–21px), giãn dòng 1.75, mỗi dòng tối đa khoảng 68 ký tự.
5. **Gần như không có chuyển động.** Chỉ dùng chuyển động 150–200ms để báo trạng thái. Không nhấp nháy, không tự chạy hiệu ứng, và tôn trọng thiết lập `prefers-reduced-motion`.
6. **Ba chế độ màu:** Sáng, Tối dịu, và Giấy (sepia, dành cho đọc lâu). Mặc định theo hệ điều hành, người dùng tự đổi được. Lựa chọn được nhớ lại.
7. **Không làm người học mất chỗ đang học.** Mở lại bài thì về đúng đoạn và đúng giây video. Quiz tự lưu từng câu. Không có hộp thoại bật ra giữa chừng, trừ khi người học sắp mất dữ liệu.
8. **Có nhắc nghỉ mắt** (theo quy tắc 20-20-20) sau mỗi 45 phút học liên tục. Lời nhắc là một thông báo nhỏ, không chặn màn hình, tắt được trong Cài đặt, và **không bao giờ hiện khi đang làm quiz có giờ**.

---

## 2. Màu (design tokens)

| Token | Sáng | Tối dịu | Giấy (sepia) | Dùng cho |
|---|---|---|---|---|
| `--background` | `#F7F5F0` | `#171A1E` | `#F3EAD7` | Nền trang |
| `--surface` (card) | `#FFFDF9` | `#1F2328` | `#F9F2E3` | Thẻ, khung đọc, panel |
| `--foreground` | `#24292F` | `#E4E1DA` | `#3A2F24` | Chữ chính |
| `--muted-foreground` | `#5B6470` | `#A3A8AF` | `#6B5B49` | Chữ phụ, nhãn, thời gian |
| `--border` | `#E3DED4` | `#33383F` | `#DDCFB4` | Viền, đường phân cách |
| `--primary` | `#0F6E66` | `#5FBFB3` | `#2F6B5E` | Nút chính, liên kết, mục đang chọn |
| `--primary-foreground` | `#FFFFFF` | `#0E1A19` | `#FFFFFF` | Chữ trên nút chính |
| `--accent` | `#A15C07` | `#E0A458` | `#8A5313` | Tiến độ, điểm nổi bật, trích dẫn nguồn |
| `--success` | `#2F7D4F` | `#7CC49A` | `#3B6E45` | Đúng, hoàn thành, đã xử lý |
| `--destructive` | `#B42318` | `#F2867A` | `#A3321F` | Xóa, lỗi, sai |

**Độ tương phản đã kiểm tra (WCAG):**

| | Chữ/nền | Chữ phụ/nền | Màu chính/nền | Chữ trên nút chính | Màu nhấn | Đỏ | Xanh lá |
|---|---|---|---|---|---|---|---|
| Sáng | 13.45 | 5.50 | 5.60 | 6.10 | 4.76 | 6.03 | 4.63 |
| Tối dịu | 13.37 | 7.30 | 7.97 | 8.12 | 8.00 | 7.04 | 8.50 |
| Giấy | 10.89 | 5.46 | 5.19 | 6.20 | 5.28 | 5.79 | 5.01 |

Tất cả đều ≥ 4.5:1 (chuẩn AA), và chữ nội dung vượt chuẩn AAA. **Không bao giờ chỉ dùng màu để truyền thông tin.** Đúng/sai luôn có thêm icon (✓/✕) và chữ đi kèm.

Màu tối dịu là **màu đã giảm độ bão hòa**, không phải đảo ngược từ màu sáng. Mắt đỡ mỏi khi học buổi tối.

---

## 3. Chữ

| Vai trò | Font | Cỡ / giãn dòng |
|---|---|---|
| Giao diện, tiêu đề | **Be Vietnam Pro** (thiết kế riêng cho tiếng Việt, dấu không bị dính) | Xem thang cỡ bên dưới |
| Nội dung bài, câu trả lời của AI | **Noto Sans** | 17px (chỉnh được 15–21px) / giãn dòng 1.75 / tối đa 68 ký tự mỗi dòng |
| Code | **JetBrains Mono** (có tiếng Việt) | 14px / giãn dòng 1.6 |

Nạp font qua `next/font/google` với `subsets: ["vietnamese", "latin"]` và `display: "swap"`.

**Thang cỡ chữ** (rem, nền 16px):

- `xs` 12px: chỉ dùng cho nhãn phụ, không bao giờ dùng cho nội dung.
- `sm` 14px, `base` 16px, `lg` 18px, `xl` 20px, `2xl` 24px, `3xl` 30px.
- Tiêu đề trang trên điện thoại 24px, desktop 30px. Độ đậm 600, không dùng 800–900.

---

## 4. Khoảng cách, bo góc, đổ bóng, chuyển động

- **Khoảng cách:** bội số của 4px. Khoảng cách giữa các khối nội dung trên trang: 24px trên điện thoại, 32px trên desktop.
- **Bo góc:** `--radius: 10px` cho thẻ và panel, 8px cho nút và ô nhập, tròn hẳn cho huy hiệu (badge).
- **Đổ bóng:** rất nhẹ, chỉ dùng cho lớp nổi (menu, dialog, panel Tutor trên điện thoại). Thẻ thường chỉ dùng viền.
- **Chuyển động:** 150ms khi hover hoặc nhấn, 200ms khi mở panel. Không có hiệu ứng khi cuộn trang. Khi `prefers-reduced-motion` bật thì tắt hết chuyển động.

---

## 5. Hệ thống nút

### 5.1 Các loại nút

| Variant | Hình thức | Khi nào dùng | Quy tắc |
|---|---|---|---|
| **Chính** (`default`) | Nền `--primary`, chữ trắng | Hành động **quan trọng nhất** của màn hình hoặc hộp thoại | **Tối đa 1 nút chính** trong mỗi vùng nhìn |
| **Phụ** (`outline`) | Viền, nền trong suốt | Hành động thay thế: Hủy, Xem trước, Làm lại, Xuất file | Đặt bên trái nút chính (desktop) hoặc phía trên nút chính (điện thoại) |
| **Nhẹ** (`ghost`) | Không viền, đổi nền khi hover | Thanh công cụ, hành động phụ lặp lại: Sao chép, 👍/👎, Đóng | Nút chỉ có icon **bắt buộc** có `aria-label` và tooltip |
| **Nguy hiểm** (`destructive-outline` → `destructive`) | Viền đỏ ngoài màn hình; nền đỏ **chỉ trong hộp thoại xác nhận** | Xóa khóa học, chương, bài, tài liệu | Luôn **tách xa** nút chính và luôn có hộp thoại xác nhận |
| **Liên kết** (`link`) | Chữ màu chính, gạch chân khi hover | Điều hướng trong câu chữ: Xem tất cả, Quay lại bài | Không dùng cho hành động thay đổi dữ liệu |

### 5.2 Kích thước và trạng thái

- **Cỡ:**
  - `default` cao 40px; trên điện thoại vùng chạm tối thiểu **44×44px** (thêm padding vô hình nếu cần).
  - `lg` cao 48px, dùng cho nút chính trên điện thoại (Nộp bài, Đăng ký).
  - `sm` cao 32px, **chỉ dùng trên desktop**, trong bảng hoặc thanh công cụ.
  - `icon` 40×40px.
- **Luôn có chữ.** Icon chỉ đứng trước chữ (icon Lucide 16px). Chỉ thanh công cụ mới được dùng nút chỉ có icon.
- **Chữ trên nút là động từ cụ thể:** "Đăng ký khóa học", "Nộp bài", "Gửi câu hỏi". Không dùng "OK", "Xác nhận" hay "Submit".
- **Các trạng thái bắt buộc:**
  - Hover: đổi nền nhẹ, 150ms.
  - Focus: vòng viền 2px màu `--primary`, cách nút 2px. **Không bao giờ được tắt.**
  - Đang xử lý: icon xoay, chữ đổi thành dạng đang làm ("Đang nộp…"), nút bị khóa để không bấm được 2 lần.
  - Bị khóa: mờ 50%, và **có giải thích lý do** qua tooltip hoặc dòng chữ bên dưới, ví dụ "Tài liệu đang được xử lý".

### 5.3 Bảng hành động → nút

**Học viên**

| Màn hình | Hành động | Variant | Icon | Khi đang xử lý | Xác nhận | Phản hồi khi xong |
|---|---|---|---|---|---|---|
| Chi tiết khóa | Đăng ký khóa học | Chính `lg` | `BookOpenCheck` | "Đang đăng ký…" | Không | Đổi thành "Vào học" và chuyển tới bài đầu tiên |
| Chi tiết khóa (đã đăng ký) | Vào học / Học tiếp | Chính `lg` | `PlayCircle` | — | Không | Mở đúng bài và đoạn đang học dở |
| Bài học | Đánh dấu đã học xong | Phụ | `CheckCircle2` | "Đang lưu…" | Không | Đổi thành "Đã học ✓", và gợi ý **Bài tiếp theo** (nút chính) |
| Bài học | Bài trước / Bài tiếp | Phụ / Chính | `ChevronLeft` / `ChevronRight` | — | Không | — |
| Bài học | Mở AI Tutor | Nhẹ (thanh công cụ), có chữ "Hỏi AI" | `MessageCircleQuestion` | — | Không | Mở panel; trên điện thoại là khung trượt từ dưới lên |
| Bài học | Chế độ tập trung | Nhẹ, chỉ icon | `Maximize2` | — | Không | Ẩn thanh bên, giữ nguyên chỗ đang đọc |
| Bài học | Cỡ chữ A− / A+ | Nhẹ, chỉ icon | `AArrowDown` / `AArrowUp` | — | Không | Đổi ngay, được nhớ lại |
| AI Tutor | Gửi câu hỏi | Chính, gắn vào ô nhập | `SendHorizontal` | Đổi thành **Dừng** (Phụ, `Square`) trong lúc AI trả lời | Không | Chữ hiện dần; nguồn trích dẫn hiện **trước** câu trả lời |
| AI Tutor | Bấm vào nguồn [n] | Liên kết | — | — | Không | Cuộn tới đúng đoạn trong bài, hoặc mở đúng trang PDF / giây video |
| AI Tutor | 👍 / 👎 | Nhẹ, chỉ icon, có `aria-pressed` | `ThumbsUp` / `ThumbsDown` | — | Không | Đổi màu, có thông báo "Cảm ơn góp ý" |
| AI Tutor | Thử lại (khi lỗi) | Phụ | `RotateCcw` | "Đang thử lại…" | Không | — |
| Quiz | Bắt đầu làm bài | Chính `lg` | `Play` | "Đang mở…" | Có, **chỉ khi** quiz tính giờ ("Bắt đầu tính giờ 15 phút?") | — |
| Quiz | Chọn đáp án | Thẻ lựa chọn cả dòng (radio), vùng chạm ≥ 48px | — | Tự lưu, hiện chữ "Đã lưu" bên cạnh | Không | — |
| Quiz | Câu trước / Câu sau | Phụ / Phụ | `ChevronLeft` / `ChevronRight` | — | Không | — |
| Quiz | Nộp bài | Chính `lg` | `Send` | "Đang nộp…" | **Có**: "Còn 2 câu chưa trả lời. Nộp bài?" | Chuyển tới trang kết quả |
| Kết quả quiz | Xem giải thích câu sai | Liên kết | — | — | Không | Mở rộng ngay tại câu đó |
| Kết quả quiz | Làm lại | Phụ | `RotateCcw` | — | Không | Ẩn nút nếu đã hết lượt làm |

**Giảng viên**

| Màn hình | Hành động | Variant | Icon | Khi đang xử lý | Xác nhận | Phản hồi khi xong |
|---|---|---|---|---|---|---|
| Khóa đang dạy | Tạo khóa học | Chính | `Plus` | "Đang tạo…" | Không | Mở trình soạn khóa |
| Trình soạn khóa | Thêm chương / Thêm bài | Phụ | `Plus` | — | Không | Ô tên mới tự được chọn để gõ ngay |
| Trình soạn khóa | Lưu nội dung bài | Tự lưu (dừng gõ 1 giây) và có nút Phụ "Lưu" | `Save` | Chữ "Đang lưu…" ở thanh trạng thái | Không | "Đã lưu lúc 14:32" |
| Trình soạn khóa | Kéo thả sắp xếp | Tay nắm `GripVertical`, kèm nút ↑↓ cho bàn phím và điện thoại | — | — | Không | Lưu ngay; lỗi thì trả về thứ tự cũ |
| Trình soạn khóa | Xem trước như học viên | Phụ | `Eye` | — | Không | Mở trang bài ở chế độ chỉ xem |
| Trình soạn khóa | Xuất bản | Chính (đặt ở thanh trên cùng, duy nhất) | `Globe` | "Đang xuất bản…" | **Có**: "Học viên sẽ thấy khóa học này" | Huy hiệu đổi từ "Nháp" sang "Đã xuất bản" |
| Trình soạn khóa | Xóa chương / bài / khóa | Nguy hiểm, nằm trong menu `⋯` | `Trash2` | — | **Có**, ghi rõ số bài hoặc tài liệu sẽ mất; với khóa học, gõ lại tên khóa để xác nhận | Thông báo "Đã xóa" |
| Tài liệu | Tải PDF lên | Phụ, kèm vùng kéo thả file | `Upload` | Thanh tiến trình % | Không | Trạng thái: Đang tải → Đang xử lý (vòng xoay) → Sẵn sàng ✓ / Lỗi |
| Tài liệu | Xử lý lại | Phụ (chỉ hiện khi Lỗi) | `RefreshCw` | "Đang gửi…" | Không | Trạng thái quay về "Đang xử lý" |
| Tài liệu | Xem các trang đã trích | Liên kết | — | — | Không | Danh sách trang, có huy hiệu Text / Vision |
| Câu hỏi (tuần 2, phần sau) | Sinh câu hỏi bằng AI | Chính | `Sparkles` | "AI đang soạn… (≈1 phút)", không khóa cả trang | Không | Thông báo khi xong, kèm số câu cần duyệt |
| Duyệt câu hỏi | Duyệt / Sửa / Loại | Chính / Phụ / Phụ | `Check` / `Pencil` / `X` | — | Không (Loại hoàn tác được trong 5 giây) | Chuyển sang câu tiếp theo |

**Chung**

| Hành động | Variant | Ghi chú |
|---|---|---|
| Đăng nhập / Đăng ký | Chính `lg`, rộng hết khung trên điện thoại | Sai mật khẩu → lỗi hiện ngay dưới ô nhập, tự đưa con trỏ về ô đó |
| Đăng xuất | Mục trong menu tài khoản, **tách riêng** cuối menu | Không đặt cạnh các mục điều hướng |
| Đổi chế độ màu | Nhóm 3 lựa chọn Sáng / Tối / Giấy (segmented) | Có ở menu tài khoản và thanh công cụ của bài học |

---

## 6. Phản hồi và trạng thái

- **Đang tải > 300ms:** hiện khung xương (skeleton) đúng hình dạng nội dung sắp hiện. Không dùng vòng xoay toàn trang.
- **Trống:** icon + một câu giải thích + **một** hành động gợi ý. Ví dụ: "Chưa có khóa học nào. [Khám phá khóa học]".
- **Lỗi:** viết bằng ngôn ngữ người dùng hiểu, kèm nút "Thử lại", và `request_id` nhỏ ở cuối để báo lỗi. Không bao giờ hiện chuỗi `{"detail": …}` thô.
- **Thông báo (toast):** góc dưới phải (desktop), trên cùng (điện thoại), tự tắt sau 4 giây, có `aria-live="polite"`, không lấy focus. Thông báo cho thao tác xóa có nút "Hoàn tác" khi làm được.
- **Hộp thoại xác nhận:** tiêu đề là câu hỏi, nội dung nói rõ hậu quả. Hai nút: Phụ "Hủy" (được focus sẵn) và Chính hoặc Nguy hiểm với động từ cụ thể.
- **Rate limit (429):** "Bạn hỏi hơi nhanh, thử lại sau 40 giây", kèm đồng hồ đếm ngược trên nút Gửi.

---

## 7. Bố cục và luồng màn hình

### 7.1 Điều hướng

- **Desktop (≥ 1024px):** thanh bên trái 240px, thu gọn được còn 64px (icon kèm tooltip). Mục theo vai trò:
  - Học viên: Trang chủ, Khám phá, Khóa của tôi.
  - Giảng viên: Khóa đang dạy, Câu hỏi chờ duyệt.
  - Admin: Duyệt giảng viên.
  - Menu tài khoản ở góc trên phải.
- **Điện thoại (< 768px):** thanh điều hướng dưới cùng, **tối đa 4 mục**, có icon và chữ. Trang bài học **ẩn thanh dưới** để có thêm chỗ đọc.
- **Tablet:** thanh bên thu gọn (icon).
- **Breadcrumb** (Khóa học › Chương › Bài) trên desktop. Trên điện thoại chỉ hiện nút ← với tên cấp cha.

### 7.2 Luồng học viên

```
Khám phá ─▶ Chi tiết khóa ─[Đăng ký]─▶ Bài 1
                                         │
Trang chủ ─[Học tiếp ▸ đúng bài, đúng chỗ]┘
                                         ▼
          Bài học ── đọc / xem video ──[Hỏi AI]──▶ Panel Tutor (bấm nguồn → cuộn tới đoạn)
             │
          [Đánh dấu đã học] ─▶ gợi ý [Bài tiếp theo]
             │
          Quiz ─[Bắt đầu]─▶ từng câu (tự lưu) ─[Nộp bài]─▶ Kết quả + giải thích câu sai
```

**Trang bài học:**

- **Desktop:** cột nội dung 68 ký tự ở giữa; mục lục khóa ở trái (thu gọn được); panel Tutor ở phải (400px, mở/đóng). Khi mở Tutor, cột nội dung **không bị co** dưới 60 ký tự; nếu màn hình hẹp, Tutor đè lên làm lớp nổi.
- **Điện thoại:** video ở trên, dính trên cùng khi cuộn (có nút thu nhỏ). Nội dung ở dưới. Nút nổi "Hỏi AI" ở góc dưới phải, mở khung trượt từ dưới lên chiếm 85% chiều cao, vuốt xuống để đóng, và giữ nguyên lịch sử chat.
- Thanh tiến độ mảnh (2px) màu `--accent` ở mép trên, cho biết đã đọc tới đâu.

### 7.3 Luồng giảng viên

```
Khóa đang dạy ─[Tạo khóa]─▶ Trình soạn khóa
                              ├─ Mục lục: chương/bài (kéo thả, ↑↓)
                              ├─ Bài: nội dung markdown (tự lưu) │ video │ tài liệu PDF (trạng thái xử lý)
                              ├─ [Xem trước như học viên]
                              └─ [Xuất bản] (xác nhận)
```

Trình soạn khóa trên desktop có 3 vùng: mục lục bên trái, nội dung bài ở giữa, thông tin và tài liệu của bài bên phải. Trên điện thoại chỉ cho xem và sửa nhẹ (tên, nội dung). Kéo thả dùng nút ↑↓ thay thế. Có dòng chữ "Soạn nội dung dài nên dùng máy tính".

---

## 8. Tính năng cho buổi học dài

| Tính năng | Mô tả | Lưu ở đâu |
|---|---|---|
| Chế độ màu Sáng / Tối dịu / Giấy | Mặc định theo hệ điều hành | `localStorage` (`next-themes`) |
| Cỡ chữ đọc 15–21px | Nút A− / A+ trên thanh công cụ của bài | `localStorage` |
| Chế độ tập trung | Ẩn thanh bên và mục lục, chỉ còn nội dung (và Tutor nếu đang mở). Phím tắt `F` | Trạng thái tạm |
| Học tiếp đúng chỗ | Lưu vị trí video (`video_position_sec`, API sẵn có) và đoạn đang đọc | Server (video), `localStorage` (vị trí cuộn) |
| Nhắc nghỉ mắt | Sau 45 phút có tương tác liên tục: "Bạn đã học 45 phút, nhìn xa 20 giây để mắt nghỉ nhé." Nút: "Đã nghỉ" / "Nhắc sau 15 phút" / "Tắt nhắc". Không hiện khi đang làm quiz | `localStorage` |
| Tự lưu có báo hiệu | Mọi nơi có tự lưu đều hiện "Đã lưu lúc …", không âm thầm | — |
| Phím tắt | `/` mở Tutor, `F` chế độ tập trung, `←` / `→` bài trước / sau, `Esc` đóng panel. Bấm `?` để xem danh sách | — |

---

## 9. Kiểm tra trước khi giao (Pre-delivery)

- [ ] Không có nền `#FFF` hoặc `#000` thuần; chữ nội dung đạt ≥ 7:1, chữ phụ ≥ 4.5:1 ở **cả 3 chế độ màu**.
- [ ] Mỗi vùng nhìn tối đa 1 nút chính; nút nguy hiểm luôn tách xa và có xác nhận.
- [ ] Mọi nút chỉ có icon đều có `aria-label` và tooltip; focus ring hiện rõ.
- [ ] Vùng chạm ≥ 44px trên điện thoại; không có cuộn ngang ở 375px.
- [ ] Mọi màn hình dữ liệu có đủ 4 trạng thái: đang tải, trống, lỗi (kèm Thử lại), có dữ liệu.
- [ ] Không có chuyển động khi bật `prefers-reduced-motion`.
- [ ] Đúng/sai/trạng thái không chỉ dựa vào màu (luôn có icon và chữ).
- [ ] Icon dùng Lucide SVG, không dùng emoji làm icon (👍/👎 cũng dùng icon Lucide).
- [ ] Kiểm tra ở 375 / 768 / 1280 / 1440px.
