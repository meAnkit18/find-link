from __future__ import annotations

from pathlib import Path

from ingestion_core.parsers.base import BaseParser, ParseOutput

MAX_TEXT_CHARS = 120_000


class TextParser(BaseParser):
    def parse(self, path: str) -> ParseOutput:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return ParseOutput(text=text[:MAX_TEXT_CHARS], structured_hint="Plain text.")
