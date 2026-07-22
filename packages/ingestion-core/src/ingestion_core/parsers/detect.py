from __future__ import annotations

import mimetypes
from pathlib import Path

from ingestion_core.parsers.base import BaseParser

# Text-only mode: file parsers (csv/pdf/docx/image) are disabled for now.
_EXT_MAP: dict[str, str] = {
    ".txt": "text", ".md": "text", ".log": "text",
}


def detect_source_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]
    guess, _ = mimetypes.guess_type(filename)
    if guess and guess.startswith("text/"):
        return "text"
    raise ValueError(
        f"Unsupported file type: {filename} (text-only mode — "
        "only pasted text and .txt/.md/.log are supported)"
    )


def get_parser(source_type: str) -> BaseParser:
    if source_type != "text":
        raise ValueError(
            f"No parser available for '{source_type}' (text-only mode)"
        )
    from ingestion_core.parsers.text_parser import TextParser
    return TextParser()
