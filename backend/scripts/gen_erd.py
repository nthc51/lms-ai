"""Sinh ERD dạng Mermaid từ SQLAlchemy metadata để sơ đồ luôn khớp với schema thật.

Dùng (từ backend/):
    uv run python -m scripts.gen_erd          # ghi docs/architecture/erd.md
    uv run python -m scripts.gen_erd --check  # CI: báo lỗi nếu file đã cũ so với models
"""

import sys
from pathlib import Path

import app.models_registry  # noqa: F401 — nạp mọi model vào metadata
from app.core.db import Base

OUT = Path(__file__).resolve().parents[2] / "docs" / "architecture" / "erd.md"


def _type_name(col) -> str:
    return type(col.type).__name__.lower()


def render() -> str:
    lines = [
        "# ERD (sinh tự động, không sửa tay)",
        "",
        "Sinh bằng `uv run python -m scripts.gen_erd` từ thư mục `backend/`. CI kiểm tra file này khớp với models.",
        "",
        "```mermaid",
        "erDiagram",
    ]
    tables = sorted(Base.metadata.sorted_tables, key=lambda t: t.name)
    for table in tables:
        lines.append(f"    {table.name} {{")
        for col in table.columns:
            keys = [k for k, on in (("PK", col.primary_key), ("FK", bool(col.foreign_keys))) if on]
            suffix = f" {', '.join(keys)}" if keys else ""
            lines.append(f"        {_type_name(col)} {col.name}{suffix}")
        lines.append("    }")
    relations = set()
    for table in tables:
        for fk in table.foreign_keys:
            cardinality = "|o--o{" if fk.parent.nullable else "||--o{"
            relations.add((fk.column.table.name, cardinality, table.name, fk.parent.name))
    for parent, cardinality, child, column in sorted(relations):
        lines.append(f'    {parent} {cardinality} {child} : "{column}"')
    lines += ["```", ""]
    return "\n".join(lines)


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != content:
            print(f"{OUT} đã cũ so với models. Chạy: uv run python -m scripts.gen_erd", file=sys.stderr)
            return 1
        print("ERD khớp với models")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"Đã ghi {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
