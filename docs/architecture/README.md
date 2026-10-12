# Kiến trúc LMS-AI

## 1. Ngữ cảnh (C4 mức 1)

```mermaid
flowchart LR
    SV([Học viên]) -->|học, hỏi AI Tutor, Studio, flashcard, ghi chú, làm quiz| LMS[Hệ thống LMS-AI]
    GV([Giảng viên]) -->|tạo khóa, tải tài liệu, duyệt quiz, sửa tài liệu AI| LMS
    AD([Quản trị viên]) -->|duyệt giảng viên, khóa tài khoản, ẩn khóa, xem token AI| LMS
    LMS -->|sinh văn bản, embedding, đọc ảnh trang PDF| GEM[(Google Gemini API)]
    LMS -->|email xác minh, thông báo| MAIL[(Brevo SMTP)]
```

## 2. Container (C4 mức 2) và triển khai

```mermaid
flowchart TB
    U([Trình duyệt]) -->|HTTPS 443| C[Caddy<br/>reverse proxy, TLS]
    subgraph VPS["VPS — mạng Docker nội bộ"]
        C -->|/| WEB[Next.js web<br/>giao diện]
        C -->|/api/*| API[FastAPI API<br/>auth, khóa học, tutor, quiz, studio, admin]
        C -->|files.*| M[(MinIO<br/>PDF, video, bài nộp)]
        C -->|grafana.*| G[Grafana]
        API --> PG[(PostgreSQL 16<br/>+ pgvector + unaccent)]
        API --> R[(Redis<br/>hàng đợi, cache, rate limit)]
        API --> M
        W[Worker arq<br/>xử lý PDF, sinh quiz, AI Studio, gửi email, sweeper] --> PG
        W --> R
        W --> M
        P[Prometheus] -->|scrape /metrics| API
        G --> P
        B[Backup<br/>pg_dump hằng ngày] --> PG
    end
    API -->|HTTPS| GEM[(Gemini API)]
    W -->|HTTPS| GEM
    W -->|SMTP 587 STARTTLS| MAIL[(Brevo)]
```

## 3. Thành phần backend (C4 mức 3)

```mermaid
flowchart LR
    subgraph API[FastAPI]
        MW[Middleware<br/>request_id, CORS, security headers, metrics]
        AUTH[auth<br/>JWT, refresh xoay vòng, xác minh email, rate limit]
        CRS[courses<br/>CRUD, catalog + cache]
        ENR[enrollment<br/>đăng ký, tiến độ, quyền xem bài]
        MAT[materials<br/>upload staging, sources]
        TUT[tutor<br/>RAG, SSE]
        QZ[quiz<br/>sinh, duyệt, làm bài]
        STU[studio<br/>hướng dẫn tài liệu, báo cáo, flashcard, ghi chú]
        ADM[admin<br/>duyệt, khóa, ẩn khóa, nhật ký, CSV]
        NTF[notify<br/>hộp thư đi email]
        JOB[jobs<br/>tạo job chống trùng]
    end
    MAT --> JOB
    QZ --> JOB
    STU --> JOB
    AUTH --> NTF
    ADM --> NTF
    TUT --> RET[retrieval<br/>vector + full-text]
    JOB -->|enqueue sau commit| Q[(Redis / arq)]
    Q --> WK[worker: ingest_pdf, source_guide, quiz_gen, studio_gen, notes_synth, gửi email, sweep_stale_jobs]
    WK --> ING[ingestion<br/>extract → chunk → embed]
```

## 4. Luồng chính

### 4.1 Tải tài liệu và xử lý PDF

```mermaid
sequenceDiagram
    actor GV as Giảng viên
    participant FE as Trình duyệt
    participant API
    participant M as MinIO
    participant DB as PostgreSQL
    participant Q as Redis/arq
    participant W as Worker
    GV->>FE: chọn file PDF
    FE->>API: POST /uploads/presign
    API->>DB: tạo asset (chưa kiểm tra)
    API-->>FE: put_url (key staging/…)
    FE->>M: PUT file vào key staging
    FE->>API: POST /uploads/{id}/complete
    API->>M: stat + đọc 2KB đầu (magic bytes)
    API->>M: copy staging → key chính thức, xóa key staging
    API-->>FE: asset đã kiểm tra
    FE->>API: POST /lessons/{id}/sources
    API->>DB: tạo source + job (cùng transaction)
    API->>Q: enqueue (sau commit)
    API-->>FE: 202 + job_id
    Q->>W: ingest_pdf
    W->>M: tải PDF
    W->>W: trích text / vision → chunk → embedding
    W->>DB: ghi pages, chunks; source = ready; job = done
    FE->>API: GET /jobs/{id} (poll)
```

### 4.2 Hỏi AI Tutor (RAG, SSE)

```mermaid
sequenceDiagram
    actor SV as Học viên
    participant API
    participant DB as PostgreSQL
    participant L as Gemini
    SV->>API: POST /tutor/sessions/{id}/messages
    API->>API: rate limit (Redis)
    API->>DB: session ngắn #1: kiểm tra quyền, lưu câu hỏi, commit
    API->>L: viết lại câu hỏi nếu có lịch sử
    API->>DB: retrieval: vector top-k lọc theo khóa/bài
    alt không đủ ngữ cảnh (dưới ngưỡng τ)
        API-->>SV: SSE done (từ chối, không gọi LLM)
    else đủ ngữ cảnh
        API-->>SV: SSE sources
        API->>L: stream câu trả lời
        L-->>API: token…
        API-->>SV: SSE token…
        API->>DB: session ngắn #2: lưu câu trả lời, citations, ttft
        API-->>SV: SSE done
    end
```

### 4.3 Làm quiz

```mermaid
sequenceDiagram
    actor SV as Học viên
    participant API
    participant DB as PostgreSQL
    SV->>API: POST /quizzes/{id}/attempts
    API->>DB: có bài dở thì trả lại bài đó, không thì tạo attempt (UNIQUE lượt làm)
    API-->>SV: câu hỏi (không kèm đáp án), deadline
    loop mỗi lần chọn đáp án
        SV->>API: PUT /attempts/{id}/answers/{qid}
        API->>DB: upsert đáp án (từ chối nếu quá deadline + 5s)
    end
    SV->>API: POST /attempts/{id}/submit (final_answers)
    API->>DB: upsert final_answers, UPDATE … WHERE status='in_progress' (chốt nguyên tử), chấm điểm
    API-->>SV: kết quả, đáp án, giải thích
```

### 4.4 Đăng ký và xác minh email

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant API
    participant DB as PostgreSQL
    participant W as Worker
    participant M as Brevo SMTP
    U->>API: POST /auth/register
    API->>API: rate limit theo IP (Redis)
    API->>DB: tạo user + token xác minh (SHA-256) + dòng email_outbox (cùng transaction)
    API-->>U: 201 (chưa đăng nhập được: 403 EMAIL_NOT_VERIFIED)
    W->>DB: nhận một email (SKIP LOCKED, có hạn giữ chỗ)
    W->>M: gửi thư
    W->>DB: sent / thử lại có backoff / failed
    U->>API: POST /auth/verify-email {token}
    API->>DB: email_verified_at = now
```

### 4.5 AI Studio: sinh tài liệu học dùng chung

```mermaid
sequenceDiagram
    actor SV as Học viên
    participant API
    participant DB as PostgreSQL
    participant W as Worker
    participant L as Gemini
    SV->>API: POST /studio/{kind}
    API->>DB: advisory lock theo phạm vi; đã có bản mới (cùng fingerprint) → trả luôn (200)
    API->>DB: rate limit 10 lần/giờ/học viên; tạo artifact (generating) + job
    API-->>SV: 202 + job_id
    W->>DB: lấy mọi đoạn của bài / khóa
    alt tài liệu ngắn
        W->>L: một lượt viết báo cáo
    else tài liệu dài
        W->>L: tóm tắt từng lô (giữ nhãn [n])
        W->>L: viết báo cáo từ các tóm tắt
    end
    W->>DB: lọc [n] không có thật, lưu nội dung + citations → ready
    SV->>API: GET /studio (poll 3 giây) → Mở
```
