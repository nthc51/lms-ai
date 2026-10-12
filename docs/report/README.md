# Báo cáo đồ án

Nội dung báo cáo viết bằng Markdown, mỗi chương một file; file Word dựng tự động từ đây.

| File | Nội dung |
|---|---|
| `00-mo-dau.md` | Bìa, lời cảm ơn, tóm tắt, từ viết tắt, mở đầu |
| `01-tong-quan.md` | Chương 1: tổng quan và cơ sở lý thuyết |
| `02-phan-tich-thiet-ke.md` | Chương 2: phân tích và thiết kế |
| `03-trien-khai.md` | Chương 3: triển khai |
| `04-kiem-thu-danh-gia.md` | Chương 4: kiểm thử và đánh giá |
| `05-ket-luan.md` | Kết luận, hướng phát triển, tài liệu tham khảo |
| `bao-cao-do-an.docx` | Bản Word dựng sẵn (A4, Times New Roman 13, lề 3/2/2/2 cm, mục lục, số trang) |

Chỗ còn thiếu được đánh dấu `[CẦN ĐIỀN: ...]` (thông tin bìa, lời cảm ơn, ảnh chụp màn hình, số liệu benchmark AI và đo tải). Tìm nhanh: `grep -n "CẦN" docs/report/*.md`.

## Quy ước khi sửa

- Tiêu đề `#` là chương (tự đánh "CHƯƠNG n."), `##` và `###` tự đánh số `n.m.` / `n.m.k.`; thêm `{.unnumbered}` để không đánh số.
- Sơ đồ viết bằng khối ` ```mermaid `, dòng đầu `%% caption: Tên hình` (tự đánh "Hình n.k"). Có thể thêm `%% size: width=14cm`.
- Ảnh chụp màn hình: đặt vào `figures/` rồi viết `![Chú thích](figures/ten-anh.png){width=15cm}` thành một đoạn riêng.

## Dựng lại file Word

Cần `pandoc` (>= 3), Python có `python-docx`, và `mmdc` (mermaid-cli, `npm i -g @mermaid-js/mermaid-cli`) nếu sửa sơ đồ; không có `mmdc` thì dùng ảnh sơ đồ đã có trong `figures/`.

```powershell
pip install python-docx
python docs/report/build/build.py
```

Mở `bao-cao-do-an.docx` bằng Word, chọn **Yes** khi được hỏi cập nhật trường để hiện mục lục (hoặc bấm vào mục lục rồi nhấn F9).
