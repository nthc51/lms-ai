::: {custom-style="Cover"}
[CẦN ĐIỀN: TÊN TRƯỜNG]

[CẦN ĐIỀN: TÊN KHOA]
:::

::: {custom-style="Cover Title"}
ĐỒ ÁN TỐT NGHIỆP
:::

::: {custom-style="Cover Title"}
XÂY DỰNG NỀN TẢNG HỌC TẬP TRỰC TUYẾN TÍCH HỢP TRỢ LÝ AI (LMS-AI)
:::

::: {custom-style="Cover"}
Sinh viên thực hiện: Nguyễn Chiến

Mã số sinh viên: [CẦN ĐIỀN]

Lớp: [CẦN ĐIỀN]

Giảng viên hướng dẫn: [CẦN ĐIỀN]

[CẦN ĐIỀN: Địa điểm], tháng [..] năm 2026
:::


<!-- MUCLUC -->

# LỜI CẢM ƠN {.unnumbered}

[CẦN ĐIỀN: lời cảm ơn giảng viên hướng dẫn, khoa, gia đình, bạn bè theo cách của bạn.]

# TÓM TẮT {.unnumbered}

Sinh viên ngày nay học chủ yếu từ slide và tài liệu PDF do giảng viên cung cấp. Khi gặp chỗ chưa hiểu, sinh viên thường phải chờ buổi học sau hoặc tự tìm trên mạng, nơi câu trả lời có thể không khớp với nội dung môn học. Ở phía giảng viên, việc soạn câu hỏi trắc nghiệm cho từng bài và tổng hợp tài liệu ôn tập tốn nhiều thời gian.

Đồ án xây dựng **LMS-AI**, một hệ thống quản lý học tập (Learning Management System) thu nhỏ có tích hợp trí tuệ nhân tạo. Giảng viên tạo khóa học, chương, bài và tải tài liệu PDF lên. Hệ thống tự đọc tài liệu (kể cả trang dạng ảnh, nhờ mô hình thị giác), chia thành các đoạn và lưu kèm vector ngữ nghĩa. Trên nền dữ liệu đó, hệ thống cung cấp:

- **AI Tutor**: trả lời câu hỏi của học viên **chỉ dựa trên tài liệu của khóa học** theo kỹ thuật RAG (Retrieval-Augmented Generation), có trích nguồn tới từng trang, trả lời dạng luồng (streaming) và từ chối khi câu hỏi nằm ngoài tài liệu. Học viên vẫn đặt được câu hỏi khi tài liệu đang xử lý; AI trả lời ngay khi xử lý xong.
- **Sinh câu hỏi trắc nghiệm bằng AI**: giảng viên chọn số câu và độ khó; AI sinh câu hỏi kèm đoạn nguồn, tự kiểm tra lại đáp án; giảng viên duyệt, sửa hoặc loại trước khi đưa vào quiz. Học viên làm quiz có tự lưu đáp án và chấm tự động.
- **AI Studio** (lấy cảm hứng từ Google NotebookLM): hướng dẫn tài liệu, đề cương ôn tập, tóm tắt, hỏi đáp, dòng thời gian, flashcard và sổ ghi chú. Mỗi nội dung được sinh một lần và dùng chung cho cả lớp.

Bên cạnh tính năng, đồ án chú trọng chất lượng hệ thống: kiến trúc khối chia module có kiểm tra ranh giới tự động, hàng đợi job nền chống trùng và tự phục hồi, email qua hộp thư đi (outbox), bảo mật theo OWASP Top 10, giám sát bằng Prometheus và Grafana, CI/CD bằng GitHub Actions với triển khai có tự động quay lui (rollback), và bộ kiểm thử gồm 751 test backend, 151 unit test frontend và 85 kịch bản end-to-end chạy ở cả khung điện thoại và máy tính.

**Từ khóa:** hệ thống quản lý học tập, RAG, mô hình ngôn ngữ lớn, pgvector, FastAPI, Next.js.

# DANH MỤC TỪ VIẾT TẮT {.unnumbered}

| Viết tắt | Đầy đủ | Ý nghĩa |
|---|---|---|
| AI | Artificial Intelligence | Trí tuệ nhân tạo |
| API | Application Programming Interface | Giao diện lập trình ứng dụng |
| CI/CD | Continuous Integration / Continuous Deployment | Tích hợp liên tục / triển khai liên tục |
| CSDL | | Cơ sở dữ liệu |
| E2E | End-to-end | Kiểm thử đầu cuối qua giao diện |
| HNSW | Hierarchical Navigable Small World | Chỉ mục tìm láng giềng gần đúng cho vector |
| JWT | JSON Web Token | Chuẩn mã thông báo đăng nhập |
| LLM | Large Language Model | Mô hình ngôn ngữ lớn |
| LMS | Learning Management System | Hệ thống quản lý học tập |
| RAG | Retrieval-Augmented Generation | Sinh văn bản có tăng cường truy xuất |
| SSE | Server-Sent Events | Cơ chế máy chủ đẩy sự kiện một chiều qua HTTP |
| TTFT | Time To First Token | Thời gian tới khi có chữ đầu tiên của câu trả lời |
| UI/UX | User Interface / User Experience | Giao diện / trải nghiệm người dùng |
| WCAG | Web Content Accessibility Guidelines | Hướng dẫn tiếp cận nội dung web |

# MỞ ĐẦU {.unnumbered}

## Lý do chọn đề tài {.unnumbered}

Các mô hình ngôn ngữ lớn như GPT, Gemini hay Claude đã đủ tốt để trả lời câu hỏi, tóm tắt và soạn bài tập. Tuy nhiên, khi dùng trực tiếp trong học tập, chúng có hai vấn đề. Thứ nhất, mô hình có thể "bịa" (hallucination): trả lời trôi chảy nhưng sai hoặc không khớp với giáo trình của môn. Thứ hai, câu trả lời không chỉ ra được nguồn, nên người học không kiểm chứng được.

Kỹ thuật RAG giải quyết cả hai vấn đề: trước khi hỏi mô hình, hệ thống tìm các đoạn liên quan trong chính tài liệu môn học rồi yêu cầu mô hình chỉ trả lời dựa trên các đoạn đó và ghi rõ nguồn. Gắn kỹ thuật này vào một hệ thống quản lý học tập hoàn chỉnh (khóa học, bài học, quiz, phân quyền) tạo ra một công cụ có ích thật cho cả người học và người dạy, đồng thời là một bài toán đủ lớn để thể hiện năng lực xây dựng hệ thống web full-stack.

So với hướng thương mại điện tử có trợ lý mua sắm (đã được cân nhắc), hướng nền tảng học tập có phần AI sâu hơn, đo lường được bằng các chỉ số rõ ràng và tự tạo được dữ liệu thử nghiệm từ tài liệu học tập sẵn có.

## Mục tiêu {.unnumbered}

1. Xây dựng hệ thống quản lý học tập với ba vai trò (học viên, giảng viên, quản trị viên): khóa học, chương, bài, tải tài liệu và video, đăng ký khóa, theo dõi tiến độ.
2. Xây dựng đường xử lý tài liệu PDF: trích chữ, đọc trang dạng ảnh bằng mô hình thị giác, chia đoạn, nhúng vector.
3. Xây dựng AI Tutor theo RAG: trích nguồn, trả lời dạng luồng, từ chối câu hỏi ngoài tài liệu.
4. Xây dựng chức năng sinh câu hỏi trắc nghiệm có giảng viên duyệt, quiz có chấm tự động, và bộ công cụ ôn tập AI Studio.
5. Bảo đảm chất lượng hệ thống: kiểm thử tự động, bảo mật, giám sát, CI/CD, giao diện đáp ứng (điện thoại và máy tính) đạt chuẩn tiếp cận WCAG AA.
6. Xây dựng công cụ đo chất lượng AI (benchmark) để chọn tham số và đánh giá bằng số liệu.

## Phạm vi {.unnumbered}

Trong phạm vi: các mục tiêu ở trên; tài liệu dạng PDF; giao diện tiếng Việt; triển khai bằng Docker trên một máy chủ.

Ngoài phạm vi: thanh toán; phát video theo luồng thích ứng (HLS); ứng dụng di động gốc; huấn luyện mô hình AI riêng (hệ thống dùng API của nhà cung cấp); chép lời video (Whisper) và chấm bài tự luận được thiết kế nhưng chưa làm, được trình bày ở phần hướng phát triển.

## Phương pháp thực hiện {.unnumbered}

- **Thiết kế trước, làm theo tầng ưu tiên:** đặc tả (design spec) được duyệt trước khi viết code; tính năng chia thành tầng A (lõi), B (mức khá), S (chất lượng hệ thống), C (điểm nhấn), làm theo thứ tự A → B → S → C để luôn có một bản nộp được.
- **Phát triển hướng kiểm thử:** mỗi tính năng có test viết trước hoặc cùng lúc với code; các trường hợp đồng thời (hai tab cùng làm bài, bấm sinh hai lần) đều có test.
- **Có trợ lý AI hỗ trợ lập trình:** kế hoạch triển khai chi tiết được viết và chạy thử trước, sau đó công cụ lập trình AI thực hiện theo kế hoạch, mỗi bước đều có kiểm thử xác nhận. Người thực hiện đồ án chịu trách nhiệm thiết kế, duyệt và kiểm thử thủ công.

## Bố cục báo cáo {.unnumbered}

- **Chương 1** trình bày tổng quan về hệ thống quản lý học tập, mô hình ngôn ngữ lớn, kỹ thuật RAG và các công nghệ sử dụng.
- **Chương 2** phân tích yêu cầu và thiết kế hệ thống: tác nhân, chức năng, kiến trúc, cơ sở dữ liệu, các luồng AI và giao diện.
- **Chương 3** trình bày quá trình triển khai backend, frontend, hạ tầng và các kỹ thuật đáng chú ý.
- **Chương 4** trình bày kiểm thử và đánh giá: kiểm thử tự động, đánh giá AI, hiệu năng, bảo mật.
- **Kết luận** tóm tắt kết quả, hạn chế và hướng phát triển.
