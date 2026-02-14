"""Backtesting engine that reuses strategy + DCA rules without real orders."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from strategy.base_strategy import StrategySettings
from utils.logger import log


@dataclass
class BacktestPosition:
    direction: str
    total_qty: float
    total_cost: float
    average_price: float
    last_order_usdt: float
    safety_orders_used: int = 0
    break_even_armed: bool = False


class BacktestEngine:
    """Runs offline trade simulation on historical Binance klines."""

    def __init__(self) -> None:
        self.dataframe: Any | None = None
        self.equity_curve: list[float] = []
        self.trade_results: list[float] = []
        self._aiohttp = None
        self.session = None

    async def load_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
    ) -> Any:
        pandas = importlib.import_module("pandas")
        if self._aiohttp is None:
            self._aiohttp = importlib.import_module("aiohttp")

        start_ms = int(datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc).timestamp() * 1000)
        params = {
            "symbol": symbol.upper(),
            "interval": timeframe,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1000,
        }

        url = "https://api.binance.com/api/v3/klines"
        rows: list[list[Any]] = []
        async with self._aiohttp.ClientSession(timeout=self._aiohttp.ClientTimeout(total=20)) as session:
            while True:
                async with session.get(url, params=params) as response:
                    payload = await response.json(content_type=None)
                    if response.status >= 400:
                        raise RuntimeError(f"Failed to load historical data: {payload}")
                    if not payload:
                        break
                    rows.extend(payload)
                    last_open = int(payload[-1][0])
                    if len(payload) < 1000 or last_open >= end_ms:
                        break
                    params["startTime"] = last_open + 1

        df = pandas.DataFrame(
            rows,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pandas.to_numeric(df[col], errors="coerce")
        df["open_time"] = pandas.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)
        self.dataframe = df
        return df

    def run_backtest(self, strategy_settings: StrategySettings) -> dict[str, float | int]:
        if self.dataframe is None or self.dataframe.empty:
            raise RuntimeError("Historical data is not loaded")

        pandas = importlib.import_module("pandas")
        importlib.import_module("pandas_ta")

        df = self.dataframe.copy()
        # vectorized pre-calculation
        df["rsi"] = df.ta.rsi(close="close", length=strategy_settings.rsi_period)
        df["ema"] = df.ta.ema(close="close", length=strategy_settings.ema_period)
        adx_df = df.ta.adx(high="high", low="low", close="close", length=strategy_settings.adx_period)
        adx_col = f"ADX_{strategy_settings.adx_period}"
        df["adx"] = adx_df[adx_col] if adx_col in adx_df.columns else None

        position: BacktestPosition | None = None
        self.equity_curve = [0.0]
        self.trade_results = []
        cumulative_pnl = 0.0

        for i in range(len(df)):
            row = df.iloc[i]
            if pandas.isna(row.get("rsi")) or pandas.isna(row.get("ema")) or pandas.isna(row.get("adx")):
                self.equity_curve.append(cumulative_pnl)
                continue

            price = float(row["close"])
            signal = None
            if row["rsi"] < strategy_settings.rsi_level and price > row["ema"] and row["adx"] > 20:
                signal = "LONG"
            elif row["rsi"] > strategy_settings.rsi_level and price < row["ema"] and row["adx"] > 20:
                signal = "SHORT"

            if position is None and signal:
                position = self.simulate_trade(
                    direction=(strategy_settings.futures_position_side.upper() if strategy_settings.enable_futures else signal),
                    usdt_amount=strategy_settings.base_order_size_usdt,
                    price=price,
                )
                self.equity_curve.append(cumulative_pnl)
                continue

            if position is None:
                self.equity_curve.append(cumulative_pnl)
                continue

            # DCA
            step = strategy_settings.safety_step_pct / 100.0
            trigger = (
                price <= position.average_price * (1 - step)
                if position.direction == "LONG"
                else price >= position.average_price * (1 + step)
            )
            if trigger and position.safety_orders_used < strategy_settings.safety_orders_count:
                next_usdt = position.last_order_usdt * strategy_settings.volume_multiplier
                added = self.simulate_trade(position.direction, next_usdt, price)
                position.total_qty += added.total_qty
                position.total_cost += added.total_cost
                position.average_price = position.total_cost / max(position.total_qty, 1e-9)
                position.last_order_usdt = next_usdt
                position.safety_orders_used += 1

            # break-even (futures only)
            if strategy_settings.enable_futures and not position.break_even_armed:
                gain_pct = (
                    (price - position.average_price) / position.average_price * 100.0
                    if position.direction == "LONG"
                    else (position.average_price - price) / position.average_price * 100.0
                )
                if gain_pct >= strategy_settings.break_even_after_percent:
                    position.break_even_armed = True

            if strategy_settings.enable_futures and position.break_even_armed:
                if (position.direction == "LONG" and price <= position.average_price) or (
                    position.direction == "SHORT" and price >= position.average_price
                ):
                    pnl = self._close_position(position, price, strategy_settings.commission_pct)
                    cumulative_pnl += pnl
                    self.trade_results.append(pnl)
                    position = None
                    self.equity_curve.append(cumulative_pnl)
                    continue

            tp = (
                position.average_price * (1 + strategy_settings.take_profit_pct / 100.0)
                if position.direction == "LONG"
                else position.average_price * (1 - strategy_settings.take_profit_pct / 100.0)
            )
            hit_tp = (price >= tp) if position.direction == "LONG" else (price <= tp)
            if hit_tp:
                pnl = self._close_position(position, price, strategy_settings.commission_pct)
                cumulative_pnl += pnl
                self.trade_results.append(pnl)
                position = None

            self.equity_curve.append(cumulative_pnl)

        report = self.generate_report()
        log(f"Backtest complete: trades={report['total_trades']} profit={report['total_profit']:.4f}")
        return report

    def simulate_trade(self, direction: str, usdt_amount: float, price: float) -> BacktestPosition:
        qty = usdt_amount / max(price, 1e-9)
        return BacktestPosition(
            direction=direction.upper(),
            total_qty=qty,
            total_cost=qty * price,
            average_price=price,
            last_order_usdt=usdt_amount,
        )

    def generate_report(self) -> dict[str, float | int]:
        total = len(self.trade_results)
        wins = [x for x in self.trade_results if x > 0]
        losses = [x for x in self.trade_results if x < 0]
        total_profit = float(sum(self.trade_results))
        win_rate = (len(wins) / total * 100.0) if total else 0.0
        avg_profit = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

        max_dd = 0.0
        peak = float("-inf")
        for equity in self.equity_curve:
            peak = max(peak, equity)
            drawdown = peak - equity
            max_dd = max(max_dd, drawdown)

        return {
            "total_trades": total,
            "win_rate": win_rate,
            "total_profit": total_profit,
            "max_drawdown": max_dd,
            "average_profit": avg_profit,
            "average_loss": avg_loss,
            "profit_factor": profit_factor,
        }

    def _close_position(self, position: BacktestPosition, exit_price: float, commission_pct: float) -> float:
        qty = position.total_qty
        commission = (commission_pct / 100.0) * qty * exit_price
        if position.direction == "LONG":
            gross = qty * exit_price
        else:
            gross = qty * (2 * position.average_price - exit_price)
        return (gross - commission) - position.total_cost
