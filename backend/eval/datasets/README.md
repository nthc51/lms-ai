# Bộ câu hỏi benchmark

Mỗi bộ gồm một file PDF (tài liệu thật, có chữ chọn được) và một file `.jsonl` cùng tên. Mỗi dòng của file
`.jsonl` là một câu hỏi:

```json
{"id": "q017", "type": "single", "question": "Đạo hàm của hàm hằng bằng bao nhiêu?", "gold_pages": [5], "gold_answer": "Bằng 0", "must_refuse": false}
```

| type | Số câu nên có | Ý nghĩa |
|---|---|---|
| `single` | ~40 | Đáp án nằm trong một đoạn |
| `multi` | ~15 | Phải ghép 2–3 đoạn (`gold_pages` có nhiều trang) |
| `paraphrase` | ~10 | Hỏi bằng từ khác tài liệu |
| `refuse` | ~15 | Ngoài tài liệu: `must_refuse: true`, `gold_pages: []` |

Dòng bắt đầu bằng `//` là chú thích. Soạn nhanh: `uv run python -m eval.draft --pdf <file> --out <file.jsonl>`,
rồi **duyệt bằng tay**.

`sample.jsonl` là bộ mẫu nhỏ đi kèm tài liệu sinh tự động trong test, chỉ để kiểm tra script.

## Bộ chấm bài (`grading-*.jsonl`, B5)

Dùng cho `uv run python -m eval.grading --dataset ...`. Mỗi dòng một bài: `title`, `instructions`, `rubric` (danh sách
`{criterion, max_points, description}`), `submission` (bài làm dạng chữ) và `human_scores` (điểm người chấm theo đúng
thứ tự rubric). Cặp kiểm tra injection: hai dòng cùng `pair`, dòng có câu "lừa" AI đặt `"injected": true`.
`grading-sample.jsonl` chỉ có 3 bài mẫu để chạy thử; bộ thật cần 15–20 bài có điểm do người chấm và 5 cặp injection.
