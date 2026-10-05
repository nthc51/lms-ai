"""Xuất OpenAPI schema ra file JSON để frontend sinh type TypeScript.

Chạy từ thư mục backend/:  uv run python -m scripts.export_openapi ../frontend/openapi.json
(Ghi file trực tiếp bằng UTF-8, không dùng `>` vì PowerShell sẽ ghi UTF-16.)"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Đã ghi {out}")


if __name__ == "__main__":
    main()
