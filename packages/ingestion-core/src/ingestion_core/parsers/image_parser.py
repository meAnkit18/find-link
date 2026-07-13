from __future__ import annotations

import pytesseract
from PIL import Image, ImageOps

from ingestion_core.parsers.base import BaseParser, ParseOutput


class ImageParser(BaseParser):
    def parse(self, path: str) -> ParseOutput:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("L")
        if max(img.size) < 1500:
            scale = 1500 / max(img.size)
            img = img.resize((int(img.width * scale), int(img.height * scale)))
        text = pytesseract.image_to_string(img)
        return ParseOutput(
            text=text,
            structured_hint=(
                "OCR output from an image \u2014 likely an identity "
                "document, form, or screenshot. OCR may contain "
                "character errors; MRZ lines (starting with P< "
                "or ID<) are machine-readable passport zones."
            ),
            metadata={"size": list(img.size)},
        )
