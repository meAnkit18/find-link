from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class CryptoWalletVertex(IntelligenceVertex):
    tag: ClassVar[str] = "crypto_wallet"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("address"):
            raise ValueError("crypto_wallet.address is required")
