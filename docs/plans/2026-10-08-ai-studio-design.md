# AI Studio (kiểu NotebookLM) và Benchmark AI: Thiết kế

> Bản thiết kế để duyệt **trước** khi viết plan chi tiết có code. Đọc xong, bạn chốt hoặc sửa các mục ở §9 ("Cần bạn quyết"), mình mới viết plan cho Claude Code.
>
> Plan này làm **sau** plan admin + email (`2026-10-07-admin-plan.md`).

## 1. Mục tiêu

Biến tài liệu giảng viên tải lên thành **bộ công cụ học**, giống NotebookLM của Google. Có hai nguyên tắc:

1. **Mọi thứ AI viết ra đều có trích nguồn** `[1]`, bấm vào xem được đúng đoạn và đúng trang trong tài liệu.
2. **Sinh một lần, dùng chung.** Đề cương, FAQ, flashcard của một bài được sinh **một lần** rồi lưu lại. 100 học viên mở thì vẫn chỉ tốn đúng một lần gọi AI. Tài liệu đổi thì sinh lại.

Ngoài ra có **benchmark** đo chất lượng AI bằng con số. Benchmark dùng để chỉnh các tham số (số đoạn gửi AI, kích thước đoạn, ngưỡng từ chối), và làm số liệu cho chương đánh giá trong báo cáo.

## 2. Các tính năng đã chọn

| # | Tính năng | Ai dùng | Ở đâu trên giao diện |
|---|---|---|---|
| S1 | **Hướng dẫn tài liệu**: tóm tắt, chủ đề chính, 5 câu hỏi gợi ý | Học viên, giảng viên | Tab "Tài liệu" của bài học; bấm câu gợi ý là hỏi AI Tutor luôn |
| S2 | **Báo cáo**: Đề cương ôn tập / Tóm tắt nhanh / Hỏi đáp (FAQ) / Dòng thời gian | Học viên | Tab "Studio" của bài học (và của cả khóa) |
| S3 | **Flashcard**: thẻ lật, đánh dấu Nhớ / Chưa nhớ, ôn lại thẻ chưa nhớ | Học viên | Tab "Studio" |
| S4 | **Sổ ghi chú**: lưu câu trả lời của AI, tự viết ghi chú, "biến ghi chú thành đề cương" | Học viên (riêng từng người) | Nút "Lưu vào ghi chú" dưới mỗi câu trả lời; trang "Ghi chú của tôi" |
| S5 | **Xem trước nguồn**: bấm `[1]` hiện đúng đoạn trích, số trang, nút "Mở PDF trang 4"; **gợi ý 3 câu hỏi tiếp theo** sau mỗi câu trả lời | Học viên | Trong khung AI Tutor |
| B | **Benchmark AI**: đo truy xuất, trích nguồn, bịa, từ chối, token, thời gian; chấm cả báo cáo và flashcard | Bạn (dev), báo cáo | Lệnh `python -m eval.run`, xuất bảng Markdown + HTML |

Đã **không chọn** (để sau): sơ đồ tư duy, podcast tổng quan, OpenRouter.

## 3. Giao diện

### 3.1 Trang bài học, desktop

Nội dung bài ở giữa, cột phải có thêm tab:

```
┌ Mục lục ┐┌────────── Nội dung bài ──────────┐┌─ [AI Tutor] [Studio] [Tài liệu] ─┐
│         ││ # Định nghĩa đạo hàm             ││ STUDIO · Bài: Định nghĩa đạo hàm │
│         ││ ...                              ││ ┌──────────┐ ┌──────────┐        │
│         ││                                  ││ │📄 Đề cương│ │❓ Hỏi đáp │        │
│         ││ ── Kiểm tra nhanh ──             ││ └──────────┘ └──────────┘        │
│         ││                                  ││ ┌──────────┐ ┌──────────┐        │
│         ││                                  ││ │⚡ Tóm tắt │ │🗂 Flashcard│       │
│         ││                                  ││ └──────────┘ └──────────┘        │
│         ││                                  ││ Phạm vi: (•) Bài này ( ) Cả khóa │
└─────────┘└──────────────────────────────────┘└──────────────────────────────────┘
```

- **Bấm một thẻ:**
  - Đã có sẵn thì mở ngay.
  - Chưa có thì hiện "AI đang soạn… (≈30 giây)". Trang không bị khóa, học tiếp được; soạn xong thì báo.
- **Báo cáo:** mở dạng trang đọc (Markdown + công thức), trích nguồn `[n]` bấm được. Có nút "Lưu vào ghi chú" và "Tải xuống (.md)".
- **Flashcard:** chế độ toàn màn hình, lật bằng phím Space, ← → để chuyển thẻ, N = nhớ, C = chưa nhớ.
- **Tab "Tài liệu":** danh sách PDF của bài, mỗi file có "Hướng dẫn": tóm tắt, chủ đề chính, câu hỏi gợi ý, nút "Mở PDF".

### 3.2 Trong AI Tutor

```
Học viên: Đạo hàm là gì?
AI: Đạo hàm là giới hạn của tỉ số gia số [1] khi h → 0 [2].
    [👍] [👎] [📌 Lưu vào ghi chú]
    Gợi ý hỏi tiếp:  (Đạo hàm một phía là gì?)  (Ví dụ tính đạo hàm x²?)  (...)
           ↑ bấm [1]:
           ┌────────────────────────────────────────┐
           │ Giáo trình Giải tích · Chương 2 · tr. 4│
           │ "Đạo hàm của hàm số f tại x₀ là giới hạn…" │
           │ [Mở PDF trang 4]                       │
           └────────────────────────────────────────┘
```

### 3.3 Sổ ghi chú (`/notes`, thêm vào menu học viên)

- Danh sách ghi chú theo khóa và bài. Mỗi ghi chú là Markdown, giữ nguyên trích nguồn nếu được lưu từ AI.
- Chọn nhiều ghi chú → **"Tạo đề cương từ ghi chú"**: AI gộp thành một đề cương. Đề cương này chỉ dùng nội dung trong ghi chú, không tìm thêm tài liệu.

### 3.4 Điện thoại (375px)

- Tab Studio / Tài liệu nằm trong khung trượt từ dưới lên, giống AI Tutor hiện tại.
- Flashcard chiếm toàn màn hình; vuốt trái/phải để chuyển thẻ, chạm để lật.

## 4. Dữ liệu (bảng mới)

```
source_guides        (source_id PK, status, summary, topics jsonb, questions jsonb,
                      content_hash, model, prompt_version, tokens_in/out, created_at)
study_artifacts      (id, course_id, lesson_id NULL=cả khóa, kind, status,
                      content_md | cards jsonb, citations jsonb,
                      fingerprint, job_id, model, prompt_version, tokens_in/out, created_at)
                      UNIQUE(course_id, lesson_id, kind, fingerprint)
flashcard_reviews    (user_id, artifact_id, card_no, known bool, reviewed_at) PK(user, artifact, card)
notes                (id, user_id, course_id, lesson_id NULL, title, content_md, citations jsonb,
                      from_message_id NULL, created_at, updated_at)
chat_messages        + followups jsonb NULL   (3 câu hỏi gợi ý, sinh lần đầu rồi lưu lại)
```

- **`kind`:** `study_guide` | `briefing` | `faq` | `timeline` | `flashcards`.
- **`fingerprint`:** băm của danh sách (chunk_id, nội dung) trong phạm vi. Giảng viên sửa hoặc xử lý lại tài liệu thì fingerprint đổi, lần mở sau tự sinh bản mới; bản cũ vẫn giữ cho tới khi bản mới xong.

## 5. API mới

| Endpoint | Ghi chú |
|---|---|
| `GET /lessons/{id}/documents` | Học viên đã đăng ký (hoặc chủ khóa): danh sách PDF đã xử lý xong + hướng dẫn (S1) |
| `GET /sources/{id}/file` | URL ký sẵn để mở PDF (thêm `#page=N` ở frontend). Chỉ học viên đã đăng ký và chủ khóa |
| `GET /chunks/{id}` | Toàn văn một đoạn + tên bài, mục, trang (xem trước nguồn S5). Kiểm quyền như AI Tutor |
| `GET /studio?course_id=&lesson_id=` | Trạng thái 5 loại tài liệu của phạm vi: `none` / `generating` / `ready` / `stale` |
| `POST /studio/{kind}` `{course_id, lesson_id?}` | Đã có bản mới nhất thì trả luôn. Chưa có thì tạo job nền, 202 `{job_id}`. Giới hạn 10 lần sinh / giờ / học viên |
| `GET /studio/artifacts/{id}` | Nội dung + trích nguồn |
| `PUT /studio/artifacts/{id}/cards/{n}` `{known}` | Đánh dấu flashcard |
| `POST /tutor/messages/{id}/followups` | 3 câu hỏi gợi ý (sinh lần đầu bằng model rẻ, sau đó đọc lại) |
| `GET/POST/PATCH/DELETE /notes`, `POST /notes/synthesize` `{note_ids}` | Sổ ghi chú; tổng hợp thành đề cương (job nền) |

## 6. Cách AI sinh nội dung (và tiết kiệm token)

| Việc | Đầu vào gửi AI | Model | Khi nào chạy |
|---|---|---|---|
| Hướng dẫn tài liệu (S1) | Tiêu đề các mục + đoạn đầu mỗi mục, tối đa ~6k token | Rẻ (flash-lite) | Tự động ngay sau khi PDF xử lý xong (job nối tiếp) |
| Báo cáo (S2) | Toàn bộ đoạn của bài nếu ≤ 12k token. Dài hơn thì **tóm tắt từng phần trước (map) rồi gộp (reduce)** | Chính | Lần đầu có người bấm |
| Flashcard (S3) | Như trên, yêu cầu JSON `[{front, back, n}]` | Chính | Lần đầu có người bấm |
| Gợi ý hỏi tiếp (S5) | Câu hỏi + câu trả lời + tên các mục liên quan (~500 token) | Rẻ | Khi frontend xin (sau `done`) |
| Đề cương từ ghi chú (S4) | Nội dung các ghi chú đã chọn | Chính | Khi học viên bấm |

**Trích nguồn trong báo cáo:**

- Đoạn tài liệu được đánh số `[1]…[n]` y như AI Tutor đang làm.
- Lọc lại các `[n]` không hợp lệ, rồi lưu `citations` gồm `chunk_id`, trang và mục.
- Frontend dùng chung component "xem trước nguồn" với AI Tutor.

**Kiểm soát chi phí (đúng câu bạn hỏi):**

- Tài liệu đã ở dạng Markdown và đã chia đoạn sẵn, AI không đọc PDF lần nào nữa.
- Sinh một lần dùng chung (§1), nên số lần gọi AI tỉ lệ với **số bài học**, không tỉ lệ với số học viên.
- Mọi lời gọi ghi lại `tokens_in` / `tokens_out` / `model` / `prompt_version`. Trang admin thêm ô **"Token AI 7 ngày"**, chia theo loại (Tutor, quiz, studio).
- Các tham số chỉnh được trong `.env`: `TUTOR_TOP_K` (số đoạn gửi đi), `CHUNK_MAX_TOKENS` (kích thước đoạn, mới), `STUDIO_MAX_INPUT_TOKENS`. Benchmark (§7) cho biết nên đặt bao nhiêu.

## 7. Benchmark AI

### 7.1 Bộ dữ liệu (`backend/eval/datasets/<tên>.jsonl`)

Bộ dữ liệu dựng trên **1–2 tài liệu thật** của bạn, ví dụ giáo trình môn học, khoảng 30–60 trang. Gồm khoảng 80 câu hỏi, mỗi câu một dòng:

```json
{"id": "q017", "type": "single", "question": "Đạo hàm của hàm hằng bằng bao nhiêu?",
 "gold_pages": [5], "gold_answer": "Bằng 0", "must_refuse": false}
```

| Loại | Số câu | Kiểm tra gì |
|---|---|---|
| `single` | ~40 | Đáp án nằm trong một đoạn |
| `multi` | ~15 | Phải ghép 2–3 đoạn |
| `paraphrase` | ~10 | Hỏi bằng từ khác tài liệu (thử khả năng tìm theo nghĩa) |
| `refuse` | ~15 | Ngoài tài liệu, AI phải từ chối (vd. "Thủ đô của Pháp?", câu gần chủ đề nhưng không có trong tài liệu) |

**Cách soạn nhanh:**

1. Chạy `python -m eval.draft --doc <file.pdf>`: AI đề xuất câu hỏi kèm trang nguồn.
2. **Bạn duyệt và sửa** trong file JSONL.
3. Tự viết thêm câu `refuse`.

Câu hỏi nên được người duyệt, không để AI tự chấm bài của chính nó.

### 7.2 Chỉ số

| Chỉ số | Ý nghĩa | Cách đo |
|---|---|---|
| **Recall@k** | Có tìm đúng đoạn chứa đáp án không | Trang của đoạn tìm được ∩ `gold_pages` |
| **Độ đúng trích nguồn** | `[n]` có trỏ tới đoạn thật sự chứa ý đó không | AI giám khảo (model khác hoặc cùng model, prompt riêng) chấm từng `[n]` |
| **Độ bám tài liệu** | Câu trả lời có ý nào **không** có trong các đoạn không (bịa) | AI giám khảo chấm 0 / 0.5 / 1 |
| **Độ đúng** | So với `gold_answer` | AI giám khảo chấm 0 / 0.5 / 1 |
| **Từ chối đúng** | Câu `refuse` có từ chối không; câu thường có bị từ chối nhầm không | Đếm trực tiếp (không cần AI) |
| **Token / câu, thời gian** | Chi phí | Lấy từ log của LLMClient |
| **Studio** | Báo cáo và flashcard có bám tài liệu, trích nguồn đúng không | AI giám khảo chấm từng câu khẳng định / từng thẻ |

### 7.3 Chạy và so sánh

```bash
python -m eval.run --dataset giai-tich --grid "top_k=4,6,8;chunk=500,700" --judge gemini-3.5-flash
```

- Mỗi cấu hình chạy hết bộ câu hỏi, rồi xuất `eval/results/<ngày>/report.md` + `report.html`.
- Bảng so sánh có các cột: cấu hình, Recall@k, Bám tài liệu, Đúng, Từ chối đúng, Token/câu, Thời gian.
- Biểu đồ **đánh đổi chất lượng và token**, để chọn cấu hình tốt nhất.
- **Quét ngưỡng từ chối** (`TUTOR_REFUSE_THRESHOLD`, hiện đang đặt tạm là 0.3) từ 0.1 đến 0.6. Chọn ngưỡng có tỉ lệ từ chối đúng cao mà ít từ chối nhầm.
- **Cache kết quả** từng câu theo (cấu hình, prompt_version), để chạy lại chỉ tốn token cho phần thay đổi. Với gói miễn phí (500 lượt/ngày cho flash-lite), mỗi lần chạy khoảng 80 câu × 2 lượt (trả lời + chấm) cho mỗi cấu hình, nên mỗi ngày chạy được vài cấu hình.
- **CI:** chạy bộ 10 câu với provider giả, chỉ để chắc script không hỏng. Không chấm điểm thật trong CI.
- **Giữ kết quả cũ** để so giữa các lần sửa prompt (`prompt_version`). Điểm giảm quá 5% thì báo đỏ.

## 8. Ước lượng công việc (Claude Code làm)

| Phần | Ngày |
|---|---|
| Nền: bảng, job `studio_gen`, fingerprint, kiểm quyền, API documents / file / chunks | 1 |
| S1 Hướng dẫn tài liệu + tab Tài liệu | 0.5 |
| S2 Báo cáo (4 loại, map-reduce cho tài liệu dài) + trang đọc | 1 |
| S3 Flashcard + chế độ ôn | 1 |
| S4 Sổ ghi chú + tổng hợp | 1 |
| S5 Xem trước nguồn + gợi ý hỏi tiếp | 0.5 |
| Ô "Token AI 7 ngày" cho admin | 0.25 |
| Benchmark: bộ chạy, giám khảo, lưới cấu hình, báo cáo HTML, quét ngưỡng | 1.5 |
| E2E + trợ năng cho mọi màn mới | 0.75 |
| **Tổng** | **~7.5 ngày** |

Bạn đang ở ngày 8/35. Thứ tự đề xuất: FE-2 → admin + email (~3 ngày) → AI Studio (~7.5 ngày). Như vậy xong khoảng ngày 20. Còn khoảng 2 tuần cho tầng S (deploy), soạn bộ câu benchmark, chạy benchmark thật và viết báo cáo.

## 9. Cần bạn quyết

1. **Học viên có được xem / tải file PDF gốc không?** Hiện chỉ giảng viên mở được PDF. Nút "Mở PDF trang 4" cần học viên xem được file.
   - **Đề xuất:** cho xem.
   - Hoặc thêm công tắc "Cho học viên tải tài liệu" ở từng tài liệu; tắt thì chỉ hiện đoạn trích.
2. **Ai được bấm sinh báo cáo / flashcard lần đầu?**
   - **Đề xuất:** học viên nào cũng được, có giới hạn 10 lần / giờ, và kết quả dùng chung.
   - Cách khác: chỉ giảng viên sinh và "xuất bản", học viên chỉ xem.
3. **Giảng viên có được sửa báo cáo / flashcard AI sinh không?**
   - **Đề xuất:** có. Sửa xong bản đó được đánh dấu "Giảng viên đã duyệt" và không bị sinh lại tự động. Thêm khoảng 0.5 ngày.
4. **Tài liệu cho benchmark:** bạn dùng giáo trình nào? Cần 1–2 file PDF có chữ chọn được (không phải bản scan), khoảng 30–60 trang.
5. **AI giám khảo:** dùng chính `gemini-3.5-flash-lite` (tiết kiệm quota nhưng "tự chấm mình", kém khách quan), hay `gemini-3.5-flash` (khách quan hơn, quota 20 lượt/ngày nên chạy rất chậm)?
   - **Đề xuất:** flash-lite cho hằng ngày. Một lần chạy cuối với model mạnh hơn (hoặc OpenRouter) để lấy số đưa vào báo cáo.
