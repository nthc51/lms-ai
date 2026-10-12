# KIỂM THỬ VÀ ĐÁNH GIÁ

## Chiến lược kiểm thử

Hệ thống có AI và nhiều thao tác bất đồng bộ, nên lỗi thường nằm ở các chỗ: AI trả lỗi hoặc trả sai định dạng, người dùng thao tác đồng thời (hai tab, bấm hai lần), job nền chết giữa chừng, và phân quyền. Chiến lược kiểm thử tập trung vào các đường đi quan trọng và các trường hợp biên đó, thay vì chạy theo tỉ lệ phủ mã.

| Loại | Công cụ | Kiểm tra gì |
|---|---|---|
| Đơn vị | pytest, Vitest | Chia đoạn, làm sạch trích dẫn, bộ lọc `REFUSE`, kiểm tra câu hỏi AI, các hàm tiện ích giao diện |
| Tích hợp | pytest + PostgreSQL thật (pgvector) + Redis | Ràng buộc CSDL, chỉ mục chống job trùng, tìm vector, bỏ dấu tiếng Việt, khóa dòng |
| API | `httpx.AsyncClient` gọi thẳng ứng dụng | Luồng chính của từng module, định dạng lỗi, mã trạng thái |
| Phân quyền | pytest | Từng vai trò với từng endpoint; truy cập tài nguyên của người khác phải trả 404 |
| Đồng thời | `asyncio.gather` | Hai tab cùng bắt đầu làm bài, nộp bài đua với tác vụ dọn, bấm sinh câu hỏi hai lần, job và cron cùng trả lời câu hỏi chờ |
| Lỗi AI | Provider giả lập có thể "gài lỗi" | 429 rồi thành công, lỗi giữa luồng, luồng rỗng, hết giờ trước chữ đầu tiên, đầu ra sai lược đồ |
| Giao diện đơn vị | Vitest + Testing Library + MSW (giả lập API) | Hook AI Tutor (luồng, dừng, đổi bài, câu hỏi chờ), tự lưu quiz, biểu mẫu |
| Đầu cuối | Playwright + axe-core | Kịch bản người dùng thật trên trình duyệt ở khung 375px và 1280px, kèm kiểm tra tiếp cận WCAG AA tự động |

Test dùng **CSDL PostgreSQL thật** (không dùng SQLite) vì nhiều tính năng dựa vào đặc thù của PostgreSQL (pgvector, chỉ mục một phần, `SKIP LOCKED`, khóa tư vấn). Test chỉ chạy trên CSDL có hậu tố `_test` để tránh xóa nhầm dữ liệu. Toàn bộ test dùng provider AI giả lập nên kết quả tất định và không tốn tiền.

## Kết quả kiểm thử tự động

| Bộ test | Số lượng | Kết quả |
|---|---|---|
| Backend (pytest, 67 file) | 751 test | 751 đạt |
| Frontend đơn vị (Vitest, 35 file) | 151 test | 151 đạt |
| Đầu cuối (Playwright, 43 kịch bản × 2 khung hình) | 86 lượt | 85 đạt, 1 bỏ qua có chủ ý |
| Kiểm tra mã | ruff, ESLint, tsc, import-linter (5 hợp đồng ranh giới) | Sạch |

Một số test tiêu biểu:

| Tình huống | Kỳ vọng | Kết quả |
|---|---|---|
| Hai tab cùng bắt đầu làm một quiz | Chỉ có một lượt làm; tab thứ hai nhận lại lượt đó | Đạt |
| Học viên nộp bài đúng lúc tác vụ dọn chốt bài | Bài chỉ được chấm một lần | Đạt |
| Giảng viên bấm "Sinh câu hỏi" hai lần liên tiếp | Một job duy nhất | Đạt |
| Worker chết khi đang xử lý PDF | Sau thời hạn, job và tài liệu chuyển "lỗi", giảng viên bấm xử lý lại được | Đạt |
| Job chưa được lưu mà đã đưa vào hàng đợi | Test giả lập hàng đợi báo lỗi ngay (quy tắc "lưu rồi mới đưa vào hàng đợi") | Đạt |
| AI trả 429 hai lần rồi mới trả lời | Tự thử lại, tôn trọng `Retry-After`, trả lời bình thường | Đạt |
| Người dùng bấm "Dừng" giữa câu trả lời | Phần đã sinh được lưu với `truncated = true` | Đạt |
| Học viên bị hủy đăng ký sau khi mở phiên hỏi | Câu hỏi mới bị từ chối 403 | Đạt |
| Học viên A đọc phiên hỏi của học viên B | 404 | Đạt |
| Tải lên file thực thi đổi đuôi thành `.pdf` | Bị từ chối, file bị xóa | Đạt |
| Refresh token đã thu hồi bị dùng lại | Mọi phiên của người dùng bị thu hồi | Đạt |
| Link đặt lại mật khẩu dùng lần thứ hai / hết hạn | `INVALID_TOKEN` / `TOKEN_EXPIRED` | Đạt |
| Câu hỏi chờ: job và cron cùng chạy | Mỗi câu chỉ được trả lời một lần, đúng thứ tự | Đạt |
| Tài liệu xử lý lỗi khi có câu hỏi chờ | Câu hỏi nhận thông báo thay vì chờ mãi | Đạt |

Các kịch bản đầu cuối gồm: khách xem danh mục và được chuyển tới đăng nhập khi đăng ký khóa; học bài, hỏi AI có trích nguồn, đánh dấu xong, sang bài tiếp; AI quá tải báo thời gian chờ; giảng viên soạn khóa, sắp xếp, xuất bản có xác nhận, tự lưu; sinh và duyệt câu hỏi, tạo quiz; học viên làm quiz có tự lưu, mở lại bài làm dở vẫn giữ đáp án, hết lượt thì báo rõ; AI Studio (báo cáo, flashcard, tài liệu, ghi chú); quản trị viên duyệt/từ chối giảng viên, khóa tài khoản, ẩn khóa; xác nhận email; quên mật khẩu; hỏi AI lúc tài liệu đang xử lý; tương phản đạt chuẩn ở cả ba chế độ màu.

## Kiểm thử thủ công

Ngoài test tự động, các tính năng được kiểm tra thủ công trên hệ thống chạy bằng Docker với email thật được bắt bởi Mailpit, ví dụ:

- Quên mật khẩu: nhận email, đặt mật khẩu mới, mật khẩu cũ không dùng được, link cũ bị từ chối, gửi quá 3 lần/giờ bị chặn, email không tồn tại vẫn báo "kiểm tra hộp thư".
- Hỏi AI lúc tài liệu đang xử lý: tải một bộ slide 174 trang (khoảng 90 giây xử lý), gửi câu hỏi khi đang xử lý, câu trả lời tự hiện khi xử lý xong.
- Sinh câu hỏi trên tài liệu thật: phát hiện lỗi chữ bị dính ở các slide xuất ra PDF (ví dụ "hiệu quảsử dụng"), đã ghi nhận và có hướng xử lý (mục hạn chế).

[CẦN ĐIỀN: thêm các lần kiểm thử thủ công khác bạn đã làm, kèm ảnh chụp.]

## Đánh giá chất lượng AI

### Công cụ benchmark

Đồ án xây dựng công cụ `backend/eval` để đo chất lượng AI Tutor bằng số liệu, thay vì đánh giá cảm tính:

1. Bộ câu hỏi (định dạng JSONL) được AI soạn nháp từ tài liệu rồi người duyệt lại; mỗi câu có trang đúng (`gold_pages`), câu trả lời tham chiếu, và loại câu (hỏi thẳng, diễn đạt khác, không dấu, ngoài phạm vi phải từ chối).
2. Công cụ xử lý PDF theo từng cấu hình, chạy toàn bộ luồng AI Tutor cho mỗi câu, rồi tính:

| Chỉ số | Ý nghĩa |
|---|---|
| Recall@k | Tỉ lệ câu mà *k* đoạn tìm được có chứa trang đúng |
| Độ đúng | Điểm giám khảo AI so với câu trả lời tham chiếu |
| Bám tài liệu (faithfulness) | Câu trả lời có được tài liệu hỗ trợ hay không, do giám khảo AI chấm |
| Độ chính xác trích dẫn | Tỉ lệ nhãn `[n]` trỏ đúng đoạn chứa nội dung |
| Từ chối đúng | Câu ngoài phạm vi đã bị từ chối |
| Từ chối nhầm | Câu trong phạm vi bị từ chối |
| Token mỗi câu, độ trễ p50/p95 | Chi phí và tốc độ |

3. **Quét lưới tham số:** số đoạn đưa vào prompt (`top_k`) × kích thước đoạn, và quét ngưỡng từ chối *τ* để vẽ đường đánh đổi giữa từ chối đúng và từ chối nhầm.
4. Xuất `report.md` và `report.html`; kết quả từng câu được lưu đệm nên chạy lại chỉ tốn chi phí cho phần mới. Lần chạy cuối dùng mô hình giám khảo mạnh hơn mô hình trả lời.

### Kết quả

[CẦN ĐIỀN SAU KHI CHẠY BENCHMARK VỚI AI THẬT (OpenRouter): bảng chỉ số theo từng cấu hình, cấu hình được chọn, ngưỡng *τ* được chọn, biểu đồ đánh đổi từ chối.]

| Cấu hình (top_k × chunk) | Recall@k | Độ đúng | Bám tài liệu | Trích dẫn đúng | Từ chối đúng | Từ chối nhầm | Token/câu | p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| 4 × 500 | | | | | | | | |
| 6 × 700 (mặc định) | | | | | | | | |
| 8 × 700 | | | | | | | | |

### Sinh câu hỏi

[CẦN ĐIỀN: trên khoảng 50 câu AI sinh từ tài liệu thật, tỉ lệ giảng viên giữ nguyên / sửa / loại; tỉ lệ câu bị gắn cờ tự kiểm tra trong số câu bị loại. Số liệu lấy từ bảng `questions` (`review_status`, `self_check_flag`).]

## Đánh giá hiệu năng

Kịch bản đo tải bằng k6 (catalog, trang chi tiết khóa, học viên đọc bài và cập nhật tiến độ) và script tạo dữ liệu mẫu (`perf_seed`) đã có sẵn.

[CẦN ĐIỀN SAU KHI ĐO: p95 và số yêu cầu/giây ở 50 người dùng ảo, trước và sau khi bật bộ nhớ đệm danh mục; TTFT p50/p95 của AI Tutor lấy từ cột `ttft_ms`.]

| Kịch bản | p95 không cache (ms) | p95 có cache (ms) | Yêu cầu/giây |
|---|---|---|---|
| Danh mục khóa học | | | |
| Chi tiết khóa học | | | |
| Học viên đọc bài + cập nhật tiến độ | | | |

[CẦN ĐIỀN: điểm Lighthouse (Performance, Accessibility, Best Practices) của trang Khám phá và trang học bài, chế độ điện thoại.]

## Đánh giá bảo mật

Hệ thống được rà soát theo OWASP Top 10 (2021); mỗi mục ghi rõ biện pháp, vị trí trong mã và test tương ứng (`docs/security/owasp-top10.md`). Tóm tắt ở mục thiết kế bảo mật (chương 2). Các điểm còn lại: CSP cho trang web hiện chỉ áp dụng ở mức Caddy cơ bản; phần phụ thuộc được quét lỗ hổng tự động trong CI nhưng chưa có quét động (DAST).

## Kết luận chương

Hệ thống có 751 test backend, 151 test giao diện đơn vị và 85 kịch bản đầu cuối, đều đạt; các trường hợp đồng thời và lỗi AI đều có test. Công cụ benchmark AI đã sẵn sàng để chọn tham số và cung cấp số liệu định lượng; số liệu đánh giá AI và hiệu năng sẽ được bổ sung sau khi chạy với AI thật và đo tải.
