# TỔNG QUAN VÀ CƠ SỞ LÝ THUYẾT

## Hệ thống quản lý học tập

### Khái niệm

Hệ thống quản lý học tập (LMS) là phần mềm giúp tổ chức, phân phối và theo dõi việc dạy học trực tuyến. Chức năng cơ bản gồm: quản lý người dùng và vai trò, tổ chức nội dung thành khóa học, chương, bài; phân phối tài liệu và video; kiểm tra đánh giá (quiz, bài tập); theo dõi tiến độ và thống kê cho người dạy.

### Một số hệ thống hiện có

- **Moodle** [1]: mã nguồn mở, phổ biến trong các trường đại học Việt Nam, rất nhiều tính năng nhờ hệ plugin. Giao diện và trải nghiệm trên điện thoại không phải thế mạnh; các tính năng AI chủ yếu đến từ plugin kết nối với nhà cung cấp bên ngoài.
- **Canvas LMS** [2]: thương mại (có bản mã nguồn mở), giao diện hiện đại, mạnh về tích hợp.
- **Google Classroom**: đơn giản, gắn với hệ sinh thái Google; ít chức năng đánh giá chuyên sâu.
- **Khan Academy – Khanmigo** [3]: trợ lý AI cho người học, hướng dẫn theo kiểu gợi mở thay vì đưa đáp án, nhưng chỉ dùng cho nội dung của Khan Academy.
- **Google NotebookLM** [4]: người dùng tải tài liệu lên, AI trả lời có trích nguồn, sinh hướng dẫn học, câu hỏi thường gặp, dòng thời gian. Đây là công cụ cá nhân, không có khái niệm khóa học, lớp học hay giảng viên duyệt nội dung.

### Khoảng trống mà đồ án hướng tới

Các LMS truyền thống chưa có trợ lý AI bám sát tài liệu của từng môn; các công cụ AI như NotebookLM lại không gắn với tổ chức lớp học. LMS-AI kết hợp hai phía: giảng viên quản lý khóa học và tài liệu như một LMS, còn AI làm việc **chỉ trên tài liệu của khóa**, có trích nguồn, và mọi nội dung AI tạo ra để đánh giá (câu hỏi quiz) đều phải qua giảng viên duyệt.

## Mô hình ngôn ngữ lớn

### Khái niệm

Mô hình ngôn ngữ lớn (LLM) là mạng nơ-ron kiến trúc Transformer [5], được huấn luyện trên lượng văn bản rất lớn để dự đoán từ (token) tiếp theo. Sau giai đoạn tinh chỉnh theo chỉ dẫn, mô hình có thể trả lời câu hỏi, tóm tắt, dịch, viết mã và sinh dữ liệu có cấu trúc theo yêu cầu. Đồ án sử dụng các mô hình họ Gemini của Google [6] qua API, có thể chuyển sang các mô hình khác qua OpenRouter [7] mà không phải sửa mã.

### Một số khái niệm khi sử dụng

- **Token:** đơn vị văn bản mà mô hình xử lý (một từ có thể là một hoặc vài token). Chi phí và giới hạn độ dài đều tính theo token.
- **Prompt:** văn bản đầu vào, gồm chỉ dẫn, ngữ cảnh và câu hỏi. Cách viết prompt (prompt engineering) ảnh hưởng lớn tới chất lượng đầu ra.
- **Temperature:** mức ngẫu nhiên khi chọn token. Đồ án dùng temperature 0 cho các tác vụ cần ổn định (sinh câu hỏi, chấm).
- **Đầu ra có cấu trúc (structured output):** yêu cầu mô hình trả về JSON theo một lược đồ (JSON Schema); hệ thống kiểm tra lại bằng Pydantic.
- **Mô hình đa phương thức (vision):** nhận cả ảnh, dùng để đọc các trang PDF dạng ảnh hoặc có công thức.
- **Ảo giác (hallucination):** mô hình sinh nội dung sai nhưng nghe hợp lý. Đây là lý do chính để dùng RAG và bắt buộc trích nguồn.

## Nhúng vector và tìm kiếm ngữ nghĩa

### Embedding

Mô hình nhúng (embedding model) biến một đoạn văn bản thành một vector số thực nhiều chiều sao cho các đoạn có nghĩa gần nhau thì vector gần nhau. Đồ án dùng vector 768 chiều (mô hình `gemini-embedding-001`, cắt về 768 chiều theo kỹ thuật Matryoshka và chuẩn hóa lại).

### Độ tương đồng cosine

Độ gần giữa hai vector *a* và *b* được đo bằng độ tương đồng cosine:

::: {custom-style="Formula"}
cos(*a*, *b*) = (*a* · *b*) / (‖*a*‖ × ‖*b*‖)
:::

Giá trị càng gần 1 thì hai đoạn càng gần nghĩa. Hệ thống dùng giá trị cao nhất của các đoạn tìm được làm căn cứ để quyết định có đủ tài liệu để trả lời hay không (ngưỡng *τ*).

### pgvector và chỉ mục HNSW

pgvector [8] là phần mở rộng của PostgreSQL thêm kiểu dữ liệu `vector` và các phép đo khoảng cách. Để tìm nhanh trên nhiều vector, pgvector hỗ trợ chỉ mục HNSW [9]: một đồ thị nhiều tầng cho phép tìm các láng giềng gần đúng với độ phức tạp gần logarit. Dùng PostgreSQL cho cả dữ liệu nghiệp vụ, vector và tìm kiếm toàn văn giúp hệ thống chỉ cần vận hành một cơ sở dữ liệu, và việc lọc theo khóa học/bài học nằm ngay trong cùng câu SQL với phép tìm vector.

### Tìm kiếm toàn văn

PostgreSQL hỗ trợ tìm kiếm toàn văn qua `tsvector`/`tsquery`. Với tiếng Việt, hệ thống bỏ dấu bằng phần mở rộng `unaccent` (bọc trong một hàm `IMMUTABLE` để dùng được trong cột sinh tự động) và dùng cấu hình `simple`, nhờ đó người học gõ không dấu vẫn tìm được. Cột `tsv` và chỉ mục GIN đã có sẵn trong lược đồ; việc kết hợp với tìm vector (hybrid search, gộp bằng Reciprocal Rank Fusion [10]) nằm trong hướng phát triển.

## Kỹ thuật RAG

RAG (Retrieval-Augmented Generation) [11] gồm hai pha:

1. **Lập chỉ mục (offline):** tài liệu được trích chữ, chia thành các đoạn (chunk) có kích thước vừa phải, nhúng thành vector và lưu lại.
2. **Truy vấn (online):** câu hỏi được nhúng thành vector, hệ thống tìm *k* đoạn gần nhất, ghép vào prompt kèm chỉ dẫn "chỉ dùng các đoạn sau, ghi nguồn [n]", rồi gửi mô hình sinh câu trả lời.

Các vấn đề thực tế mà đồ án phải xử lý:

- **Câu hỏi nối tiếp:** câu như "còn cái thứ hai thì sao?" không tìm được tài liệu nếu đứng một mình. Hệ thống dùng lịch sử hội thoại để viết lại thành câu hỏi đầy đủ trước khi tìm.
- **Câu hỏi ngoài phạm vi:** nếu đoạn gần nhất vẫn quá xa (dưới ngưỡng *τ*), hệ thống từ chối ngay mà không gọi mô hình; nếu mô hình thấy ngữ cảnh không đủ, nó trả về một mã từ chối quy ước.
- **Trích dẫn sai:** mô hình có thể ghi `[7]` khi chỉ có 6 nguồn. Hệ thống làm sạch, chỉ giữ các trích dẫn có thật.
- **Kích thước đoạn:** đoạn quá ngắn mất ngữ cảnh, quá dài thì loãng và tốn token. Đồ án chia theo tiêu đề, mỗi đoạn tối đa khoảng 700 token, chồng lấn 100 token, và có công cụ benchmark để so sánh các cấu hình.

## Các công nghệ sử dụng

### Backend

- **Python 3.12 và FastAPI** [12]: framework web bất đồng bộ, tự sinh tài liệu OpenAPI từ khai báo kiểu Pydantic. Bất đồng bộ phù hợp với hệ thống gọi nhiều API AI có độ trễ cao và trả lời dạng luồng.
- **SQLAlchemy 2 (async) và Alembic:** ánh xạ đối tượng – quan hệ và quản lý phiên bản lược đồ CSDL (20 migration).
- **PostgreSQL 16 + pgvector + unaccent:** dữ liệu nghiệp vụ, vector và tìm kiếm toàn văn.
- **Redis và arq:** arq là thư viện hàng đợi job bất đồng bộ trên Redis, nhẹ hơn Celery và dùng `async/await` tự nhiên. Redis cũng dùng cho giới hạn tần suất (rate limit) và bộ nhớ đệm.
- **MinIO:** lưu trữ đối tượng tương thích S3 cho PDF, video; trình duyệt tải lên trực tiếp bằng URL ký sẵn.
- **PyMuPDF và pymupdf4llm:** trích chữ PDF thành Markdown, giữ tiêu đề và bảng.

### Frontend

- **Next.js 16 (App Router) và React 19** [13]: dựng giao diện, định tuyến, kết xuất phía máy chủ.
- **TypeScript và openapi-typescript:** kiểu dữ liệu của API được sinh tự động từ OpenAPI của backend; backend đổi API thì frontend báo lỗi kiểu ngay khi biên dịch.
- **TanStack Query:** quản lý dữ liệu từ máy chủ (bộ nhớ đệm, tải lại, thăm dò trạng thái job).
- **Tailwind CSS và Radix UI:** giao diện theo một hệ thống thiết kế riêng, các thành phần hộp thoại, menu đạt chuẩn tiếp cận.
- **react-markdown, KaTeX:** hiển thị nội dung bài và câu trả lời của AI có công thức toán.

### Kiểm thử, triển khai, vận hành

- **pytest, Vitest, Playwright, axe-core:** kiểm thử backend, kiểm thử đơn vị frontend, kiểm thử đầu cuối trên trình duyệt thật và kiểm tra tiếp cận tự động.
- **Docker Compose:** đóng gói toàn bộ hệ thống (web, api, worker, db, redis, minio, mailpit) để chạy giống nhau trên máy phát triển và máy chủ.
- **GitHub Actions:** CI chạy kiểm tra mã, test, build image, quét lỗ hổng phụ thuộc; CD triển khai lên máy chủ qua SSH.
- **Caddy:** reverse proxy tự cấp chứng chỉ HTTPS.
- **Prometheus và Grafana:** thu thập và hiển thị số liệu vận hành.

## Kết luận chương

Chương này đã trình bày bối cảnh của các hệ thống quản lý học tập, khoảng trống giữa LMS truyền thống và các công cụ AI, cùng nền tảng lý thuyết của mô hình ngôn ngữ lớn, nhúng vector và kỹ thuật RAG. Các công nghệ được chọn ưu tiên sự đơn giản khi vận hành (một CSDL cho cả dữ liệu và vector, một hàng đợi nhẹ) và khả năng kiểm thử. Chương tiếp theo trình bày việc phân tích yêu cầu và thiết kế hệ thống trên nền tảng này.
