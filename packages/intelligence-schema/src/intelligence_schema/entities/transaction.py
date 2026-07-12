from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class TransactionVertex(IntelligenceVertex):
    tag: ClassVar[str] = "transaction"

    def validate(self) -> None:
        super().validate()
        if self.properties.get("amount") is None:
            raise ValueError("transaction.amount is required")
