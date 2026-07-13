from __future__ import annotations

import io

import fitz
import pytesseract
from PIL import Image

from ingestion_core.parsers.base import BaseParser, ParseOutput

MAX_TEXT_CHARS = 120_000
OCR_MIN_CHARS_PER_PAGE = 30


class PdfParser(BaseParser):
    def parse(self, path: str) -> ParseOutput:
        doc = fitz.open(path)
        pages, ocr_pages = [], 0
        for page in doc:
            text = page.get_text("text").strip()
            if len(text) < OCR_MIN_CHARS_PER_PAGE:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img).strip()
                ocr_pages += 1
            pages.append(f"[page {page.number + 1}]\n{text}")
        doc.close()
        full = "\n\n".join(pages)[:MAX_TEXT_CHARS]
        return ParseOutput(
            text=full,
            structured_hint=f"PDF, {len(pages)} pages ({ocr_pages} via OCR).",
            metadata={"pages": len(pages), "ocr_pages": ocr_pages},
        )
