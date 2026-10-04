"""Prompt có đánh phiên bản (spec K8).

Mỗi file <name>.md gồm front matter `version: vN` rồi đến thân prompt, placeholder viết `$ten_bien`
(string.Template: giá trị thay vào không bị xử lý lại, nên nội dung tài liệu có ký tự `$` vẫn an toàn).
Kết quả AI lưu kèm prompt_version = "<name>@<version>" để so sánh các phiên bản trong báo cáo."""

import re
import string
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
# Chấp nhận cả CRLF (file bị checkout/sửa trên Windows); phần thân giữ nguyên như trong file.
_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\nversion:[ \t]*(\S+)[ \t]*\r?\n---[ \t]*\r?\n")


@dataclass(frozen=True)
class RenderedPrompt:
    name: str
    version: str
    text: str

    @property
    def prompt_version(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    body: str

    @property
    def prompt_version(self) -> str:
        return f"{self.name}@{self.version}"

    def render(self, **values: object) -> RenderedPrompt:
        """Thay mọi placeholder; thiếu biến nào thì KeyError (không âm thầm gửi prompt thiếu dữ liệu)."""
        text = string.Template(self.body).substitute({k: str(v) for k, v in values.items()})
        return RenderedPrompt(self.name, self.version, text)


@lru_cache
def load_prompt(name: str) -> PromptTemplate:
    raw = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    m = _FRONT_MATTER.match(raw)
    if m is None:
        raise ValueError(f"Prompt {name}.md thiếu front matter 'version'")
    return PromptTemplate(name=name, version=m.group(1), body=raw[m.end() :])
