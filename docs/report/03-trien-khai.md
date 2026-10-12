# TRIỂN KHAI HỆ THỐNG

## Môi trường và tổ chức mã nguồn

### Công cụ phát triển

| Thành phần | Phiên bản / công cụ |
|---|---|
| Ngôn ngữ backend | Python 3.12, quản lý gói bằng `uv` (khóa phiên bản trong `uv.lock`) |
| Ngôn ngữ frontend | TypeScript, Node.js, `npm ci` theo `package-lock.json` |
| CSDL | PostgreSQL 16 + pgvector (image `pgvector/pgvector:pg16`) |
| Hàng đợi, bộ nhớ đệm | Redis 7 |
| Lưu trữ file | MinIO (ghim phiên bản) |
| Email khi phát triển | Mailpit (bắt mọi thư, xem tại `localhost:8025`); khi chạy thật dùng Brevo SMTP |
| Kiểm tra mã | ruff (Python), ESLint, `tsc`, import-linter |
| Hệ điều hành phát triển | Windows + Docker Desktop |

Toàn bộ hệ thống chạy bằng một lệnh `docker compose up -d`; mọi cổng chỉ mở trên `127.0.0.1`.

### Cấu trúc thư mục

```
lms-ai/
├── backend/
│   ├── app/
│   │   ├── core/        cấu hình, CSDL, lỗi, middleware, phân quyền, lưu trữ, cache, metrics
│   │   ├── ai/          provider (giả lập, Gemini, OpenRouter), LLMClient, prompts/*.md, retrieval
│   │   ├── ingestion/   trích PDF, chia đoạn, pipeline
│   │   ├── modules/     auth, courses, enrollment, materials, jobs, notify,
│   │   │                tutor, quiz, studio, analytics, admin
│   │   └── worker/      khai báo job nền và tác vụ định kỳ cho arq
│   ├── alembic/         20 migration
│   ├── eval/            công cụ benchmark AI
│   ├── scripts/         xuất OpenAPI, sinh ERD, nhúng lại, kiểm tra provider, dữ liệu đo tải
│   └── tests/           67 file test
├── frontend/
│   ├── src/app/         25 trang (App Router)
│   ├── src/components/  ui, app, content + theo tính năng (course, lesson, tutor, quiz, studio, teach, admin)
│   ├── src/lib/         gọi API, truy vấn, đăng nhập, tiện ích
│   └── e2e/             kịch bản Playwright
├── infra/               Caddy, Prometheus, Grafana, sao lưu, script triển khai
├── docs/                đặc tả, kiến trúc, bảo mật, kế hoạch triển khai
├── docker-compose.yml, docker-compose.prod.yml
└── .github/workflows/   ci.yml, deploy.yml
```

Quy mô mã nguồn: khoảng 12.300 dòng Python cho ứng dụng và 10.200 dòng cho test; khoảng 12.500 dòng TypeScript cho frontend (không tính file kiểu sinh tự động).

### Cấu trúc một module backend

Mỗi module gồm: `models.py` (bảng SQLAlchemy), `schemas.py` (dữ liệu vào/ra Pydantic, không nhận trường lạ), `service.py` (nghiệp vụ, không phụ thuộc HTTP), `router.py` (endpoint mỏng: nhận request, gọi service, trả schema). Cách tách này cho phép test nghiệp vụ trực tiếp và cho phép worker gọi lại service mà không qua HTTP.

## Triển khai các chức năng nền

### Xác thực và tài khoản

- Mật khẩu băm bằng argon2 (thư viện `pwdlib`).
- Access token JWT 15 phút; refresh token ngẫu nhiên 32 byte, lưu băm SHA-256, gửi trong cookie `HttpOnly` chỉ cho đường dẫn `/api/v1/auth`. Mỗi lần làm mới, token cũ bị thu hồi và cấp token mới; nếu một token đã thu hồi bị dùng lại, toàn bộ phiên của người dùng bị thu hồi.
- **Xác nhận email:** khi đăng ký, hệ thống tạo token (lưu băm), ghi một dòng vào hộp thư đi **trong cùng giao dịch** với tài khoản mới; người dùng chưa xác nhận không đăng nhập được. Giảng viên chỉ vào hàng chờ duyệt sau khi xác nhận email.
- **Quên mật khẩu:** luôn trả `202` để không lộ email nào đã đăng ký; link có hiệu lực 60 phút, dùng một lần; xin link mới thì link cũ vô hiệu; đặt mật khẩu mới thì mọi phiên đăng nhập cũ bị thu hồi. Giới hạn 3 lần/giờ/email và 10 lần/giờ/IP.
- **Giới hạn tần suất** bằng bộ đếm Redis cửa sổ cố định (`INCR` + `EXPIRE NX`): đăng nhập 20 lần/phút/IP (rộng tay vì cả lớp dùng chung một IP ở mạng trường), đăng ký 20 lần/giờ/IP, AI Tutor 30 câu/giờ/học viên. Redis lỗi thì cho qua (fail-open) để không chặn toàn hệ thống.

### Hộp thư đi (outbox) cho email

Email không được gửi ngay trong request mà ghi vào bảng `email_outbox` cùng giao dịch với thay đổi nghiệp vụ, nên không có trường hợp tài khoản tạo xong mà email bị mất, hoặc email đã gửi mà giao dịch bị hủy. Worker nhận từng thư bằng `SELECT ... FOR UPDATE SKIP LOCKED` (nhiều worker không nhận trùng), đặt "hạn giữ chỗ" rồi mới gửi SMTP; lỗi thì thử lại có giãn cách, tối đa 5 lần. Sau khi gửi, nội dung các thư chứa link bí mật (xác nhận email, đặt lại mật khẩu) bị xóa khỏi CSDL.

```python
mail = await db.scalar(
    select(EmailOutbox)
    .where(EmailOutbox.status == EmailStatus.pending,
           or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now))
    .order_by(EmailOutbox.created_at, EmailOutbox.id)
    .limit(1)
    .with_for_update(skip_locked=True)
)
```

API "đánh thức" worker ngay sau khi ghi thư; một tác vụ định kỳ mỗi phút vét các thư còn sót.

### Tải file lên

1. Trình duyệt xin URL ký sẵn; URL chỉ cho phép ghi vào **vùng tạm** `staging/<key>`.
2. Trình duyệt tải file thẳng lên MinIO, có thanh tiến độ.
3. Khi trình duyệt báo hoàn tất, máy chủ khóa dòng asset, **chép** file từ vùng tạm sang vị trí chính thức rồi mới kiểm tra trên bản chính thức: kích thước, và 2KB đầu để nhận diện loại file thật (magic bytes). Không hợp lệ thì xóa cả hai bản và trả lỗi.

Chép trước rồi kiểm tra sau bảo đảm người dùng không thể ghi đè file độc hại vào giữa lúc kiểm tra và lúc chấp nhận. Tên file gốc được làm sạch (bỏ đường dẫn, ký tự điều khiển) và dùng khi tải về theo chuẩn RFC 6266 (`filename*=UTF-8''...`) để giữ đúng tên tiếng Việt.

### Hệ thống job nền

- **Tạo job chống trùng:** `INSERT ... ON CONFLICT DO NOTHING RETURNING id` trên chỉ mục duy nhất một phần `uq_active_job`; nếu đã có job đang chạy cho cùng đối tượng thì trả lại job đó. Bấm "Sinh câu hỏi" hai lần chỉ tạo một job.
- **Chỉ đưa vào hàng đợi sau khi giao dịch hoàn tất**, để worker không bao giờ nhận job chưa tồn tại trong CSDL (có test kiểm tra quy tắc này).
- **Nhận job nguyên tử:** worker chuyển job sang `processing` bằng câu `UPDATE ... WHERE status IN ('pending','processing') RETURNING`; job đã kết thúc không bao giờ bị chạy lại.
- **Thời gian chờ hai lớp:** mỗi loại job có thời gian tối đa riêng (xử lý PDF 600 giây, sinh câu hỏi 900 giây...). Handler bị hủy sớm hơn 30 giây để kịp ghi trạng thái lỗi cùng giao dịch với tài liệu, thay vì để arq hủy đột ngột.
- **Tác vụ dọn job treo** (5 phút/lần): job `processing` quá hạn thì chuyển `failed` "Worker bị gián đoạn"; job `pending` bị kẹt (mất trong Redis) thì đưa lại vào hàng đợi đúng một lần, vẫn kẹt thì chuyển `failed`. Tài liệu tương ứng cũng chuyển `failed` trong cùng giao dịch để giảng viên bấm "Xử lý lại".

Các loại job: `ingest_pdf`, `quiz_gen`, `source_guide`, `studio_gen`, `notes_synth`, `tutor_waiting`; các tác vụ định kỳ: dọn job treo, gửi email, vét câu hỏi chờ.

## Triển khai các chức năng AI

### Lớp provider

Ba giao diện `LLMProvider` (sinh văn bản, sinh dạng luồng), `Embedder` (nhúng), `VisionExtractor` (đọc ảnh trang) có ba cài đặt:

- **Giả lập (`fake`):** trả kết quả tất định, không gọi mạng. Dùng khi phát triển và trong toàn bộ test, nên test chạy nhanh, ổn định và không tốn tiền.
- **Gemini:** qua SDK `google-genai`.
- **OpenRouter:** qua API kiểu OpenAI (`/chat/completions` có luồng SSE, `/embeddings`), dùng khi thẻ thanh toán không được Google AI Studio chấp nhận. Lớp này xử lý các khác biệt của OpenRouter: lỗi trả về trong thân với mã 200, dòng chú thích giữ kết nối trong luồng, số token ở sự kiện cuối, cắt vector về đúng số chiều rồi chuẩn hóa.

Đổi nhà cung cấp chỉ cần sửa `.env`; thiếu API key thì ứng dụng từ chối khởi động với thông báo rõ ràng. Khi đổi mô hình nhúng, script `reembed` tính lại vector cho các đoạn cũ mà không phải đọc lại PDF.

### Xử lý tài liệu

```python
for page_no, markdown, formula_count in _extract_text_pages(doc):
    if not needs_vision(markdown, formula_count):
        method = "text"
    elif vision_used >= max_vision_pages:
        method = "skipped"      # vượt trần: dùng chữ thường, ghi cảnh báo
    else:
        vision_used += 1
        method = "vision"
```

Toàn bộ phần PyMuPDF (trích chữ, kết xuất ảnh) chạy trong một luồng riêng để không chặn vòng lặp sự kiện của worker. Các trang cần mô hình thị giác được gọi song song có giới hạn (semaphore). Lỗi tạm thời của dịch vụ AI ở một trang chỉ làm trang đó dùng chữ thường; lỗi cấu hình thì hủy các lời gọi còn lại và báo lỗi cho cả tài liệu. Bộ chia đoạn coi khối mã là một khối nguyên, chỉ cắt cứng theo dòng khi khối quá dài.

### AI Tutor và luồng SSE

Endpoint trả `StreamingResponse` với kiểu `text/event-stream` và header chống đệm (`X-Accel-Buffering: no`). Các sự kiện: `sources` (danh sách nguồn, gửi trước), `token` (từng mảnh chữ), `done` (nội dung đã làm sạch, trích dẫn, id tin nhắn) hoặc `error`. Một số chi tiết triển khai:

- **Hạn chót trước chữ đầu tiên:** viết lại câu hỏi, tìm tài liệu và mở luồng phải xong trong 60 giây (kể cả thử lại), quá hạn thì gửi `error`.
- **Bộ lọc từ chối:** mô hình được dặn trả về đúng chữ `REFUSE` khi ngữ cảnh không đủ; bộ lọc giữ lại phần đầu của luồng cho tới khi chắc chắn không phải `REFUSE`, nên người dùng không bao giờ thấy chữ này.
- **Lưu luôn thành công:** câu trả lời được lưu trong khối `finally` bên trong `CancelScope(shield=True)` của anyio, nên kể cả khi người dùng ngắt kết nối giữa chừng, phần đã sinh vẫn được lưu với `truncated = true`.
- **Không giữ kết nối CSDL khi chờ AI:** câu hỏi được lưu và giao dịch đóng trước khi gọi mô hình; tìm tài liệu và lưu câu trả lời dùng phiên ngắn riêng. Một câu trả lời dài vài chục giây không chiếm một kết nối CSDL.

Phía giao diện, câu trả lời được đọc bằng `fetch` + `ReadableStream` (vì cần gửi `POST` có header `Authorization`, điều `EventSource` không làm được), nút "Dừng" gọi `AbortController.abort()`.

### Câu hỏi chờ khi tài liệu đang xử lý

`GET /tutor/availability` trả thêm `state` (`ready`, `processing`, `model_mismatch`, `failed`, `empty`, `draft`), số tài liệu đang xử lý và cờ `can_queue`. Khi `can_queue`, giao diện gửi câu hỏi qua `POST /tutor/sessions/{id}/questions` thay vì mở luồng. Worker nhận từng câu bằng câu lệnh cập nhật có điều kiện:

```python
claimed = (await db.execute(
    update(ChatMessage)
    .where(ChatMessage.id == message_id, ChatMessage.waiting_for_docs)
    .values(waiting_for_docs=False)
    .returning(ChatMessage.content, ChatMessage.created_at)
)).first()
```

Câu trả lời được ghi với `created_at` bằng đúng thời điểm của câu hỏi; vì danh sách tin nhắn sắp theo (thời gian, vai trò) với "user" đứng trước "assistant", câu trả lời luôn nằm ngay dưới câu hỏi dù được sinh sau các câu khác.

### Sinh câu hỏi và quiz

Job `quiz_gen` chạy các bước ở mục thiết kế, ghi toàn bộ câu hỏi và trạng thái job **trong cùng một giao dịch cuối**, nên job bị dừng giữa chừng không để lại câu hỏi dở dang. Khi sinh lại cho cùng bài, prompt kèm tối đa 20 câu đã có ("không lặp lại các câu sau") và ưu tiên các đoạn chưa được dùng.

Khi học viên làm quiz:

- Bắt đầu làm khi đang có lượt dở thì trả lại lượt đó (hai tab không tạo hai lượt).
- Mỗi lần chọn đáp án gửi ngay một yêu cầu lưu; giao diện xếp các lần lưu của cùng một câu thành hàng đợi tuần tự để yêu cầu cũ không ghi đè đáp án mới, đồng thời giữ bản sao trong `localStorage`.
- Nộp bài gửi kèm toàn bộ đáp án cuối cùng; máy chủ chốt bài bằng `UPDATE ... WHERE status='in_progress' RETURNING` rồi mới chấm, trong cùng giao dịch.

### AI Studio

Khi học viên yêu cầu một báo cáo, máy chủ lấy khóa tư vấn theo phạm vi (`pg_advisory_xact_lock(hashtext(key))`), kiểm tra đã có bản mới (cùng fingerprint của tập đoạn) thì trả luôn, nếu chưa mới kiểm tra giới hạn 10 lần/giờ và tạo job. Worker gom toàn bộ đoạn của bài/khóa; nếu tổng vượt 12.000 token thì tóm tắt từng lô (giữ nhãn `[n]`) rồi viết báo cáo từ các bản tóm tắt. Các nhãn `[n]` không có thật bị loại trước khi lưu. Flashcard lưu riêng trạng thái "nhớ / chưa nhớ" của từng học viên.

## Triển khai giao diện

### Tổ chức

- **Kiểu dữ liệu sinh từ API:** `npm run gen:api` xuất OpenAPI từ backend và sinh `schema.d.ts`; client `openapi-fetch` dùng kiểu này cho mọi lời gọi. CI kiểm tra file kiểu luôn khớp với backend.
- **Dữ liệu máy chủ** qua TanStack Query: bộ nhớ đệm, tải lại khi cần, thăm dò trạng thái job/tài liệu mỗi vài giây khi đang xử lý.
- **Đăng nhập:** access token giữ trong bộ nhớ; gặp `401` thì tự làm mới một lần rồi gọi lại, vẫn lỗi thì chuyển về trang đăng nhập.
- **Ranh giới thư mục:** `lib` và các thành phần dùng chung không được import thành phần của tính năng; quy tắc kiểm bằng ESLint.

### Các điểm trải nghiệm đáng chú ý

- **Trang học bài** nhớ vị trí video và vị trí cuộn; tài liệu PDF xem được ngay trong trang (điện thoại mở thẻ mới) và tải về đúng tên gốc, kể cả lúc AI chưa đọc xong.
- **Trợ lý học tập** ở cột phải (máy tính) hoặc khung trượt từ dưới lên (điện thoại), 4 tab: AI Tutor, Studio, Tài liệu, Ghi chú. Trích dẫn `[n]` mở thẻ xem đoạn nguồn kèm số trang.
- **Bốn trạng thái** cho mọi màn hình dữ liệu: khung xương khi tải, trạng thái trống có hướng dẫn, lỗi có nút thử lại, có dữ liệu.
- **Phím tắt** khi học: `F` chế độ tập trung, `/` mở AI Tutor, `←`/`→` chuyển bài, `?` xem danh sách phím; flashcard dùng Space để lật, N/C để đánh dấu.
- **Tiếp cận:** mọi nút có nhãn cho trình đọc màn hình; tiêu đề nhận focus khi đổi trạng thái; tôn trọng thiết lập giảm chuyển động.

## Triển khai hạ tầng và vận hành

### Đóng gói và triển khai

`docker-compose.prod.yml` gồm: `db`, `redis` (có mật khẩu), `minio`, `api`, `worker`, `web`, `caddy`, `prometheus`, `grafana`, `backup`. Chỉ `caddy` mở cổng 80/443; các dịch vụ khác nằm trong mạng nội bộ. Mỗi dịch vụ có kiểm tra sức khỏe và `restart: unless-stopped`. API có `/health` (tiến trình còn sống) và `/ready` (CSDL, Redis, MinIO đều kết nối được).

Script `infra/deploy/deploy.sh <commit>` triển khai đúng một commit và **chỉ khởi động lại phần bị đổi**: sửa `backend/` thì khởi động lại `api` và `worker`, sửa `frontend/` thì `web`, sửa hạ tầng thì cả hệ thống, sửa tài liệu thì không gì. Nếu sau khoảng 2 phút API hoặc web chưa sẵn sàng, script tự quay về commit chạy tốt gần nhất. Migration chỉ thêm (không xóa/đổi tên trong cùng một lần) để việc quay lui mã không cần hạ lược đồ.

### CI/CD

Workflow `ci.yml` có các job:

| Job | Nội dung | Chạy khi |
|---|---|---|
| `changes` | Xác định phần nào bị đổi (`dorny/paths-filter`) | Luôn |
| `lint` | ruff, kiểm tra định dạng, import-linter | Đổi backend |
| `test` | pytest với Postgres pgvector và Redis thật | Đổi backend |
| `frontend` | Kiểm tra file kiểu khớp API, ESLint, tsc, Vitest, E2E Playwright (build bản chạy thật) | Đổi backend hoặc frontend |
| `docker` | Build image | Đổi mã |
| `audit` | `pip-audit`, `npm audit` | Đổi mã |
| `infra` | actionlint, shellcheck, test script triển khai | Đổi hạ tầng |

Workflow `deploy.yml` chỉ chạy khi CI trên nhánh `main` thành công, kết nối máy chủ qua SSH và gọi `deploy.sh` với đúng commit đã qua CI.

### Giám sát và sao lưu

- **Prometheus** thu số liệu HTTP (số yêu cầu, độ trễ theo phân vị, mã lỗi) và các số liệu riêng: số job đang chờ / lỗi, email chờ / lỗi, token AI theo loại tác vụ.
- **Grafana** có dashboard dựng sẵn từ file: yêu cầu/giây, độ trễ p50/p95, tỉ lệ lỗi 5xx, hàng đợi job, TTFT của AI Tutor.
- **Sao lưu** `pg_dump` hằng ngày kèm nén dữ liệu MinIO, giữ 7 ngày; script `restore-check.sh` khôi phục bản sao lưu vào một CSDL tạm để kiểm tra bản sao lưu dùng được.

### Quy trình phát triển có trợ lý AI

Mỗi nhóm tính năng được viết thành một kế hoạch triển khai (`docs/plans/`) gồm các task nhỏ, mỗi task có test viết trước, mã, lệnh kiểm tra và kết quả mong đợi. Mã trong kế hoạch được chạy thử trên một bản sao của dự án trước khi giao cho công cụ lập trình AI thực hiện; sau khi thực hiện, kết quả được đối chiếu lại với bản đã chạy thử. Người thực hiện đồ án duyệt thiết kế, kiểm thử thủ công từng tính năng và quyết định các đánh đổi.

## Kết luận chương

Chương này đã trình bày cách hiện thực các thiết kế ở chương 2: các chức năng nền (xác thực, email qua outbox, tải file an toàn, job nền tự phục hồi), các chức năng AI (lớp provider đổi được, xử lý tài liệu, AI Tutor dạng luồng, câu hỏi chờ, sinh câu hỏi, AI Studio), giao diện và hạ tầng vận hành. Chương tiếp theo trình bày việc kiểm thử và đánh giá hệ thống.
