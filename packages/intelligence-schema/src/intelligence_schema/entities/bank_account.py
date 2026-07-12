from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class BankAccountVertex(IntelligenceVertex):
    tag: ClassVar[str] = "bank_account"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("account_number"):
            raise ValueError("bank_account.account_number is required")
