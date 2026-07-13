from __future__ import annotations

import mimetypes
from pathlib import Path

from ingestion_core.parsers.base import BaseParser
from ingestion_core.parsers.csv_parser import CsvParser
from ingestion_core.parsers.docx_parser import DocxParser
from ingestion_core.parsers.image_parser import ImageParser
from ingestion_core.parsers.pdf_parser import PdfParser
from ingestion_core.parsers.text_parser import TextParser

_EXT_MAP: dict[str, str] = {
    ".csv": "csv", ".tsv": "csv",
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "text", ".md": "text", ".log": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".tif": "image", ".tiff": "image", ".bmp": "image", ".webp": "image",
}

_PARSERS: dict[str, BaseParser] = {
    "csv": CsvParser(),
    "pdf": PdfParser(),
    "docx": DocxParser(),
    "image": ImageParser(),
    "text": TextParser(),
}


def detect_source_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]
    guess, _ = mimetypes.guess_type(filename)
    if guess:
        if guess.startswith("image/"):
            return "image"
        if guess == "application/pdf":
            return "pdf"
        if guess.startswith("text/"):
            return "text"
    raise ValueError(f"Unsupported file type: {filename}")


def get_parser(source_type: str) -> BaseParser:
    try:
        return _PARSERS[source_type]
    except KeyError as e:
        raise ValueError(f"No parser registered for '{source_type}'") from e
