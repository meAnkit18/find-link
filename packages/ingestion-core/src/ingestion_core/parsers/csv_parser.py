from __future__ import annotations

import pandas as pd

from ingestion_core.parsers.base import BaseParser, ParseOutput

MAX_ROWS = 500
MAX_TEXT_CHARS = 60_000


class CsvParser(BaseParser):
    def parse(self, path: str) -> ParseOutput:
        sep = "\t" if path.lower().endswith(".tsv") else ","
        df = pd.read_csv(
            path, sep=sep, dtype=str, keep_default_na=False,
            nrows=MAX_ROWS, on_bad_lines="skip", encoding_errors="replace",
        )
        lines = []
        for i, row in df.iterrows():
            pairs = "; ".join(f"{c}={v}" for c, v in row.items() if str(v).strip())
            lines.append(f"[row {i + 1}] {pairs}")
        text = "\n".join(lines)[:MAX_TEXT_CHARS]
        hint = (
            f"CSV with columns: {list(df.columns)}. "
            f"{len(df)} rows parsed. Each line is one record; "
            f"treat repeated values across rows as the same entity."
        )
        return ParseOutput(
            text=text, structured_hint=hint,
            metadata={"columns": list(df.columns), "rows": len(df)},
        )
