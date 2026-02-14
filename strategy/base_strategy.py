"""Base strategy implementation for signal generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy.indicators import IndicatorEngine


@dataclass
class StrategySettings:
    """Runtime strategy settings taken from the UI."""

    rsi_period: int = 14
    rsi_level: float = 30.0
    ema_period: int = 200
    adx_period: int = 14
    timeframe: str = "1m"

    take_profit_pct: float = 1.0
    base_order_size_usdt: float = 25.0
    order_timeout_sec: int = 30
    use_market_order: bool = True

    safety_step_pct: float = 2.0
    safety_orders_count: int = 3
    volume_multiplier: float = 1.5
    commission_pct: float = 0.1

    enable_futures: bool = False
    leverage: int = 5
    margin_mode: str = "Cross"  # Cross / Isolated
    break_even_after_percent: float = 0.3
    futures_position_side: str = "Long"  # Long / Short
    mode: str = "Spot"
    cooldown_minutes: float = 0.0
    anti_reentry_threshold_pct: float = 0.2
    run_mode: str = "Live"  # Live / Paper / Backtest

    use_rsi: bool = True
    use_ema_trend_filter: bool = True
    use_adx_filter: bool = True
    use_volume_filter: bool = False
    use_atr_filter: bool = False
    adx_threshold: float = 20.0
    volume_spike_multiplier: float = 1.5
    atr_min_value: float = 0.0
    position_size_mode: str = "Fixed"  # Fixed / Risk-based
    risk_per_trade_pct: float = 1.0
    max_total_exposure_pct: float = 30.0
    protection_orders_on_exchange: bool = True
    enable_stop_loss: bool = False
    stop_loss_mode: str = "Off"  # Off / Always / After Last Safety
    stop_loss_pct: float = 1.0
    auto_resume_running_pairs: bool = False


class ConditionEngine:
    """Evaluates enabled strategy conditions and builds signal diagnostics."""

    def __init__(self) -> None:
        self.indicators = IndicatorEngine()

    def evaluate_conditions(self, df: Any, settings: StrategySettings, direction: str) -> tuple[bool, dict[str, bool | None]]:
        checks: dict[str, bool | None] = {
            "RSI": self.check_rsi(df, settings, direction) if settings.use_rsi else None,
            "EMA": self.check_ema_trend(df, settings, direction) if settings.use_ema_trend_filter else None,
            "ADX": self.check_adx(df, settings) if settings.use_adx_filter else None,
            "Volume": self.check_volume_spike(df, settings) if settings.use_volume_filter else None,
            "ATR": self.check_atr_filter(df, settings) if settings.use_atr_filter else None,
        }

        enabled = [value for value in checks.values() if value is not None]
        if not enabled:
            return False, checks
        return all(enabled), checks

    def check_rsi(self, df: Any, settings: StrategySettings, direction: str) -> bool:
        rsi = self.indicators.calculate_rsi(df, settings.rsi_period)
        if rsi is None:
            return False
        if direction == "LONG":
            return rsi < settings.rsi_level
        return rsi > settings.rsi_level

    def check_ema_trend(self, df: Any, settings: StrategySettings, direction: str) -> bool:
        ema = self.indicators.calculate_ema(df, settings.ema_period)
        if ema is None:
            return False
        close_price = float(df["close"].iloc[-1])
        if direction == "LONG":
            return close_price > ema
        return close_price < ema

    def check_adx(self, df: Any, settings: StrategySettings) -> bool:
        adx = self.indicators.calculate_adx(df, settings.adx_period)
        if adx is None:
            return False
        return adx > settings.adx_threshold

    def check_volume_spike(self, df: Any, settings: StrategySettings) -> bool:
        if len(df.index) < 2:
            return False
        current_volume = float(df["volume"].iloc[-1])
        avg_volume = float(df["volume"].iloc[:-1].tail(20).mean())
        if avg_volume <= 0:
            return False
        return current_volume > avg_volume * settings.volume_spike_multiplier

    def check_atr_filter(self, df: Any, settings: StrategySettings) -> bool:
        atr = self.indicators.calculate_atr(df, settings.adx_period)
        if atr is None:
            return False
        return atr > settings.atr_min_value


class BaseStrategy:
    """Signal generator based on configurable condition engine."""

    def __init__(self, settings: StrategySettings) -> None:
        self.settings = settings
        self.condition_engine = ConditionEngine()
        self.last_condition_report: dict[str, dict[str, bool | None] | str] = {}

    def _format_report(self, checks: dict[str, bool | None]) -> str:
        parts: list[str] = []
        for name, value in checks.items():
            if value is True:
                parts.append(f"{name} ✔")
            elif value is False:
                parts.append(f"{name} ✘")
            else:
                parts.append(f"{name} -")
        return " ".join(parts)

    def generate_signal(self, df: Any) -> str | None:
        """Return LONG/SHORT signal or None based on enabled condition filters."""
        if df is None or df.empty:
            return None

        long_ok, long_checks = self.condition_engine.evaluate_conditions(df, self.settings, "LONG")
        short_ok, short_checks = self.condition_engine.evaluate_conditions(df, self.settings, "SHORT")

        self.last_condition_report = {
            "LONG": long_checks,
            "SHORT": short_checks,
            "LONG_TEXT": self._format_report(long_checks),
            "SHORT_TEXT": self._format_report(short_checks),
        }

        if long_ok:
            return "LONG"
        if short_ok:
            return "SHORT"
        return None
