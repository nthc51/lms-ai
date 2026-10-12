# KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN {.unnumbered}

## Kết quả đạt được {.unnumbered}

Đồ án đã xây dựng hệ thống LMS-AI chạy được đầy đủ trên Docker, gồm:

- **Hệ thống quản lý học tập** với ba vai trò: khóa học, chương, bài; tải PDF và video; đăng ký khóa, theo dõi tiến độ; xác nhận email, quên mật khẩu; khu quản trị (duyệt giảng viên, khóa tài khoản, ẩn khóa học, nhật ký, xuất CSV, theo dõi chi phí AI).
- **Đường xử lý tài liệu** đọc được cả trang chữ lẫn trang ảnh và công thức (mô hình thị giác), có trần chi phí, chạy nền, tự phục hồi khi worker gặp sự cố.
- **AI Tutor theo RAG** chỉ trả lời từ tài liệu khóa học, trích nguồn tới trang, trả lời dạng luồng, từ chối câu ngoài phạm vi, không mất dữ liệu khi lỗi hay khi người dùng ngắt; cho phép đặt câu hỏi khi tài liệu đang xử lý.
- **Sinh câu hỏi trắc nghiệm** có tự kiểm tra và giảng viên duyệt; **quiz** có tự lưu, chấm tự động, giải thích.
- **AI Studio**: hướng dẫn tài liệu, đề cương, tóm tắt, hỏi đáp, dòng thời gian, flashcard, sổ ghi chú; nội dung sinh một lần dùng chung cho cả lớp.
- **Chất lượng hệ thống:** kiến trúc khối chia module có kiểm tra ranh giới tự động; 751 test backend, 151 test giao diện, 85 kịch bản đầu cuối có kiểm tra tiếp cận; CI chạy theo phần bị đổi; triển khai chỉ khởi động lại phần bị đổi và tự quay lui khi lỗi; giám sát Prometheus/Grafana; sao lưu hằng ngày; rà soát OWASP Top 10.
- **Đổi nhà cung cấp AI không cần sửa mã:** giả lập, Gemini hoặc OpenRouter, chọn bằng cấu hình.
- **Công cụ benchmark AI** để chọn tham số và đánh giá bằng số liệu.

## Hạn chế {.unnumbered}

- **Truy xuất mới dùng tìm vector.** Tìm kiếm toàn văn đã có trong lược đồ nhưng chưa được kết hợp (hybrid search); câu hỏi chứa thuật ngữ hiếm hoặc mã số có thể bị bỏ sót.
- **Chữ bị dính ở một số PDF xuất từ slide:** lớp chữ của các file này thiếu dấu cách giữa các khối chữ, khiến đoạn văn khó đọc với AI. Đang có hướng xử lý: chèn dấu cách dựa trên khoảng cách vị trí giữa các ký tự khi trích chữ.
- **Chưa có số liệu đánh giá AI và hiệu năng trên môi trường thật** tại thời điểm viết báo cáo (cần chạy benchmark với AI trả phí và đo tải).
- **Chưa triển khai trên máy chủ thật:** cấu hình, script triển khai và quay lui đã có và đã kiểm thử cục bộ.
- Một số chức năng trong thiết kế ban đầu chưa làm: quiz tính giờ và xáo trộn, giải thích câu sai bằng AI, thảo luận theo bài, bài tập tự luận có AI gợi ý chấm, thông báo thời gian thực, chép lời video và trích dẫn theo mốc thời gian, chứng chỉ.

## Hướng phát triển {.unnumbered}

1. **Hybrid search:** kết hợp tìm vector và tìm toàn văn, gộp bằng Reciprocal Rank Fusion; đo lại Recall@k bằng công cụ benchmark.
2. **Video:** chép lời bằng Whisper, chia đoạn theo thời gian, trích dẫn bấm vào thì video nhảy đúng giây.
3. **Bài tập tự luận:** AI gợi ý chấm theo rubric, có trích dẫn bằng chứng từ bài làm, chống chèn lệnh trong bài làm; giảng viên xác nhận điểm.
4. **Quiz nâng cao:** tính giờ, xáo trộn, làm lại; AI giải thích câu sai có trích nguồn.
5. **Học thích ứng:** lặp lại ngắt quãng (SM-2) cho flashcard, gợi ý bài cần ôn theo kết quả quiz.
6. **Cộng đồng:** thảo luận theo bài, thông báo thời gian thực.
7. **Vận hành:** reranker cho kết quả tìm kiếm, chạy mô hình nhúng tại chỗ để giảm chi phí, phát video theo luồng thích ứng, ứng dụng di động.

# TÀI LIỆU THAM KHẢO {.unnumbered}

[1] Moodle Pty Ltd, *Moodle Documentation*, https://docs.moodle.org

[2] Instructure, *Canvas LMS*, https://www.instructure.com/canvas

[3] Khan Academy, *Khanmigo*, https://www.khanmigo.ai

[4] Google, *NotebookLM*, https://notebooklm.google

[5] A. Vaswani et al., "Attention Is All You Need," *Advances in Neural Information Processing Systems*, 2017.

[6] Google, *Gemini API Documentation*, https://ai.google.dev/gemini-api/docs

[7] OpenRouter, *OpenRouter Documentation*, https://openrouter.ai/docs

[8] A. Kane, *pgvector: Open-source vector similarity search for Postgres*, https://github.com/pgvector/pgvector

[9] Y. A. Malkov and D. A. Yashunin, "Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs," *IEEE Transactions on Pattern Analysis and Machine Intelligence*, vol. 42, no. 4, 2020.

[10] G. V. Cormack, C. L. A. Clarke and S. Büttcher, "Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods," *SIGIR*, 2009.

[11] P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," *Advances in Neural Information Processing Systems*, 2020.

[12] S. Ramírez, *FastAPI Documentation*, https://fastapi.tiangolo.com

[13] Vercel, *Next.js Documentation*, https://nextjs.org/docs

[14] OWASP Foundation, *OWASP Top 10: 2021*, https://owasp.org/Top10/

[15] W3C, *Web Content Accessibility Guidelines (WCAG) 2.2*, https://www.w3.org/TR/WCAG22/

[16] PostgreSQL Global Development Group, *PostgreSQL 16 Documentation: Full Text Search*, https://www.postgresql.org/docs/16/textsearch.html
