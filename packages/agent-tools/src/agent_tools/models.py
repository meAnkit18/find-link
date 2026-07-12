from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any]
    message: str
