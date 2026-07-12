"""Sniff a CSV's dialect and infer a per-column type profile from a sample.

Pure, file-I/O-only module: no NebulaGraph/graph-core knowledge here at
all — this just turns a CSV file into structured facts about its columns,
consumed by structure_inference.py.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field

SAMPLE_ROWS = 500

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_BOOL_VALUES = {"true", "false", "yes", "no"}


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str  # "int" | "float" | "bool" | "string"
    null_ratio: float
    distinct_ratio: float
    sample_values: list[str] = field(default_factory=list)


@dataclass
class InspectionResult:
    headers: list[str]
    columns: list[ColumnProfile]
    sample_rows: list[dict[str, str]]
    delimiter: str


def _sniff_delimiter(sample_text: str) -> str:
    try:
        return csv.Sniffer().sniff(sample_text, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _infer_type(values: list[str]) -> str:
    non_null = [v for v in values if v != ""]
    if not non_null:
        return "string"
    if all(v.lower() in _BOOL_VALUES for v in non_null):
        return "bool"
    if all(_INT_RE.match(v) for v in non_null):
        return "int"
    if all(_FLOAT_RE.match(v) for v in non_null):
        return "float"
    return "string"


def inspect_csv(path: str, encoding: str = "utf-8-sig") -> InspectionResult:
    with open(path, encoding=encoding, newline="") as f:
        head = f.read(65536)
    delimiter = _sniff_delimiter(head) if head.strip() else ","

    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        headers = reader.fieldnames or []
        sample_rows: list[dict[str, str]] = []
        for row in reader:
            sample_rows.append({k: (v or "") for k, v in row.items() if k is not None})
            if len(sample_rows) >= SAMPLE_ROWS:
                break

    columns: list[ColumnProfile] = []
    total = len(sample_rows) or 1
    for header in headers:
        values = [row.get(header, "") for row in sample_rows]
        non_null = [v for v in values if v != ""]
        null_ratio = 1 - (len(non_null) / total)
        distinct_ratio = (len(set(non_null)) / len(non_null)) if non_null else 0.0
        columns.append(
            ColumnProfile(
                name=header,
                inferred_type=_infer_type(values),
                null_ratio=null_ratio,
                distinct_ratio=distinct_ratio,
                sample_values=non_null[:5],
            )
        )

    return InspectionResult(
        headers=headers, columns=columns, sample_rows=sample_rows, delimiter=delimiter
    )
