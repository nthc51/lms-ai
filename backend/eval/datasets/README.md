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
