"""Bybit exchange adapter placeholder."""

from __future__ import annotations

from typing import Any

from exchanges.base_exchange import BaseExchange
from utils.logger import log


class BybitExchange(BaseExchange):
    """Bybit implementation placeholder."""

    async def connect(self) -> None:
        log("Bybit not implemented yet")

    async def check_connection(self) -> bool:
        log("Bybit not implemented yet")
        return False

    async def get_balance(self, asset: str = "USDT") -> float | None:
        log("Bybit not implemented yet")
        return None

    async def place_order(self, **kwargs: Any) -> dict:
        log("Bybit not implemented yet")
        return {}

    async def cancel_order(self, **kwargs: Any) -> dict:
        log("Bybit not implemented yet")
        return {}

    async def get_order_status(self, **kwargs: Any) -> dict:
        log("Bybit not implemented yet")
        return {}

    async def get_position(self, **kwargs: Any) -> dict:
        log("Bybit not implemented yet")
        return {}

    async def set_leverage(self, symbol: str, leverage: int) -> dict:
        log("Bybit not implemented yet")
        return {}

    async def set_margin_type(self, symbol: str, margin_type: str) -> dict:
        log("Bybit not implemented yet")
        return {}
