"""Technical indicators engine based on pandas and pandas-ta."""

from __future__ import annotations

import importlib
from typing import Any


class IndicatorEngine:
    """Calculates technical indicators from OHLCV candle DataFrames."""

    def _load_pandas(self) -> Any | None:
        try:
            return importlib.import_module("pandas")
        except ModuleNotFoundError:
            return None

    def _ensure_ta(self) -> bool:
        try:
            importlib.import_module("pandas_ta")
            return True
        except ModuleNotFoundError:
            return False

    def calculate_rsi(self, dataframe: Any, period: int) -> float | None:
        """Return RSI value of the latest candle."""
        if self._load_pandas() is None or not self._ensure_ta():
            return None

        series = dataframe.ta.rsi(close="close", length=period)
        if series is None or series.dropna().empty:
            return None
        return float(series.dropna().iloc[-1])

    def calculate_ema(self, dataframe: Any, period: int) -> float | None:
        """Return EMA value of the latest candle."""
        if self._load_pandas() is None or not self._ensure_ta():
            return None

        series = dataframe.ta.ema(close="close", length=period)
        if series is None or series.dropna().empty:
            return None
        return float(series.dropna().iloc[-1])

    def calculate_adx(self, dataframe: Any, period: int) -> float | None:
        """Return ADX value of the latest candle."""
        if self._load_pandas() is None or not self._ensure_ta():
            return None

        adx_df = dataframe.ta.adx(high="high", low="low", close="close", length=period)
        if adx_df is None or adx_df.empty:
            return None

        adx_column = f"ADX_{period}"
        if adx_column not in adx_df.columns:
            return None

        series = adx_df[adx_column].dropna()
        if series.empty:
            return None
        return float(series.iloc[-1])

    def calculate_atr(self, dataframe: Any, period: int) -> float | None:
        """Return ATR value of the latest candle."""
        if self._load_pandas() is None or not self._ensure_ta():
            return None

        series = dataframe.ta.atr(high="high", low="low", close="close", length=period)
        if series is None or series.dropna().empty:
            return None
        return float(series.dropna().iloc[-1])
