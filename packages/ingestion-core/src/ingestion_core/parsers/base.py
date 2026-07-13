from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParseOutput:
    text: str
    structured_hint: str = ""
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    @abstractmethod
    def parse(self, path: str) -> ParseOutput:
        ...
