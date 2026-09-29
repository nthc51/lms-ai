# Bổ sung spec: Chất lượng hệ thống và Frontend

- **Ngày:** 2026-09-29
- **Áp dụng cho:** `docs/specs/2026-09-29-lms-ai-design.md`
- **Nguyên tắc:** không cắt tính năng nào, chỉ thêm tầng S và xếp thứ tự ưu tiên.

---

## 1. Thứ tự ưu tiên mới

**A (lõi) → B (mức Khá) → S (chất lượng hệ thống) → C (điểm nhấn)**

Tầng S đứng trước tầng C, vì đồ án tập trung vào xây dựng hệ thống. Hết thời gian mà vẫn còn việc thì phần trễ là tầng C, không phải S. Tuần 5 vẫn giữ cho báo cáo và bộ đánh giá như cũ.

## 2. Tầng S: Chất lượng hệ thống (thêm vào bảng tiến độ, mục 0)

- [ ] **S1. CI:** GitHub Actions chạy ruff, pytest (có service Postgres pgvector) và build image Docker cho mỗi lần push và PR.
- [ ] **S2. Deploy production:** VPS với Caddy (HTTPS tự động) và file `docker-compose.prod.yml`, gồm healthcheck, `restart: unless-stopped`, secrets lấy từ `.env` trên server. Backup `pg_dump` hằng ngày, giữ bản của 7 ngày gần nhất, và **đã thử khôi phục** ít nhất một lần.
- [ ] **S3. CD:** push lên `main` và CI xanh thì tự deploy lên VPS (qua SSH action), chạy `alembic upgrade head` trước khi khởi động lại API.
- [ ] **S4. Giám sát:**
  - `/health` (tiến trình còn sống) và `/ready` (DB, Redis, MinIO đều kết nối được).
  - Thu metrics Prometheus (`prometheus-fastapi-instrumentator`, cộng metric riêng cho số job trong hàng đợi và số job lỗi).
  - Dashboard Grafana gồm: số request/giây, độ trễ p50/p95, tỉ lệ lỗi 5xx, job đang chờ và job lỗi, thời gian tới token đầu tiên (TTFT) của AI Tutor.
- [ ] **S5. Hiệu năng:**
  - Viết kịch bản load test k6 cho catalog, trang chi tiết khóa học, đọc bài học và làm quiz.
  - Báo cáo p95 và throughput ở mức 50 người dùng ảo.
  - Cache catalog và trang chi tiết khóa học bằng Redis (TTL 60 giây, xóa cache khi publish hoặc sửa khóa). So sánh số liệu trước và sau khi cache.
- [ ] **S6. Bảo mật:**
  - Rate limit cho `/auth/login` và `/auth/register` (ví dụ 10 lần/phút/IP).
  - Cấu hình CORS cho đúng origin của frontend.
  - Security headers: HSTS, X-Content-Type-Options, CSP cơ bản.
  - Rà theo checklist OWASP Top 10. Mỗi mục ghi rõ "đã xử lý ở đâu" hoặc "chưa xử lý, lý do".
- [ ] **S7. Tài liệu kiến trúc:** sơ đồ C4 (mức Context, Container, Component), ERD, sequence diagram cho 4 luồng: upload + xử lý tài liệu, hỏi AI Tutor, làm quiz, nộp + chấm bài.

Ước lượng khoảng 6–7 ngày. S1 nên làm sớm, ngay sau khi backend tuần 1 xong, vì làm sớm thì phát huy tác dụng lâu nhất.

## 3. Yêu cầu Frontend (bổ sung vào mục 3 của spec)

| Yêu cầu | Chi tiết |
|---|---|
| Responsive | Các mốc 375 / 768 / 1280px. Học viên ưu tiên điện thoại: trang học bài có video ở trên, AI Tutor mở dạng khung trượt từ dưới lên. Giảng viên ưu tiên desktop, nhưng trên tablet vẫn dùng được. |
| 4 trạng thái | Mọi màn hình dữ liệu có đủ: đang tải (skeleton), trống, lỗi kèm nút thử lại, có dữ liệu. |
| Phản hồi realtime | Tiến trình upload, trạng thái xử lý tài liệu (dựa trên `/jobs/{id}`), câu trả lời AI Tutor hiện dần theo luồng. |
| Giao diện | Chế độ sáng/tối, tiếng Việt, dùng được bằng bàn phím, độ tương phản đạt chuẩn WCAG AA. |
| Design system | Chốt bằng `ui-ux-pro-max`: màu, font, khoảng cách, component shadcn/ui. |

## 4. Đánh giá bổ sung (thêm vào mục 9 của spec)

- **9.7 Hệ thống:**
  - p95 và throughput từ k6 (so sánh trước và sau khi cache).
  - Độ phủ test (`pytest --cov`).
  - Số lần build và deploy thành công trên CI.
  - Thời gian khôi phục từ file backup.
- **9.8 Frontend:**
  - Điểm Lighthouse (Performance, Accessibility, Best Practices) của 5 trang chính, mục tiêu ≥ 90.
  - Test E2E Playwright chạy qua ở cả khung điện thoại (375px) và desktop (1280px).

## 5. Lịch cập nhật

| Tuần | Việc chính | Tầng S đi kèm |
|---|---|---|
| 1 | A1–A4 backend (đang chạy) | S1 CI ngay khi xong tuần 1 |
| 2 | A5–A8 và frontend lõi | S7 bắt đầu vẽ ERD và C4 |
| 3 | B1–B8 | S6 bảo mật |
| 4 | S2–S5 deploy, CD, giám sát, hiệu năng, sau đó đến C1, C2 | |
| 5 | Dùng thử, đánh giá, báo cáo | Chạy lại k6 và Lighthouse trên bản chốt |

Tầng C làm sau S trong tuần 4. Nếu tuần 4 không kịp thì C1 (Whisper) chuyển sang đầu tuần 5 hoặc ghi vào mục "Hướng phát triển". Tuần 5 vẫn không bị lấn.

## 6. Nhật ký quyết định (thêm vào mục 13 của spec)

| Ngày | Quyết định |
|---|---|
| 2026-09-29 | Đồ án nhấn mạnh xây dựng hệ thống. Thêm tầng S (CI/CD, deploy, giám sát, hiệu năng, bảo mật, tài liệu kiến trúc) và yêu cầu frontend (responsive, 4 trạng thái, Lighthouse). Không cắt tính năng; thứ tự ưu tiên là A → B → S → C. |
