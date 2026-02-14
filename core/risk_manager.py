"""Risk manager module."""

from __future__ import annotations


class RiskManager:
    """Tracks simple loss streak risk rule."""

    def __init__(self) -> None:
        self.consecutive_losses = 0

    def initialize(self) -> None:
        self.consecutive_losses = 0

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def shutdown(self) -> None:
        return

    def register_trade_result(self, pnl: float) -> bool:
        """Return True when risk rule requires stopping all pairs."""
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        return self.consecutive_losses >= 3
