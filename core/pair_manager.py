"""Pair manager module with independent async workers."""

from __future__ import annotations

import asyncio
import importlib
import traceback
from collections.abc import Callable

from core.order_manager import OrderManager
from core.websocket_manager import Candle, WebSocketManager
from exchanges.base_exchange import BaseExchange
from strategy.base_strategy import BaseStrategy, StrategySettings
from strategy.indicators import IndicatorEngine
from utils.logger import log


class PairWorker:
    """Independent async worker for one trading pair."""

    def __init__(
        self,
        pair_name: str,
        mode: str,
        exchange_name: str,
        exchange: BaseExchange,
        websocket_manager: WebSocketManager,
        order_manager: OrderManager,
        settings: StrategySettings,
        on_trade_closed: Callable[[str, float, str, str], None],
        on_price_update: Callable[[str, float], None] | None = None,
        exposure_provider: Callable[[], float] | None = None,
        on_runtime_update: Callable[[str], None] | None = None,
    ) -> None:
        self.pair_name = pair_name
        self.mode = mode
        self.exchange_name = exchange_name
        self.exchange = exchange
        self.websocket_manager = websocket_manager
        self.order_manager = order_manager
        self.on_trade_closed = on_trade_closed
        self.on_price_update = on_price_update
        self._exposure_provider = exposure_provider
        self._on_runtime_update = on_runtime_update
        self.strategy_settings = settings
        self.strategy = BaseStrategy(settings)
        self.indicator_engine = IndicatorEngine()

        self.running = False
        self.candles: list[Candle] = []
        self._last_candle_version = 0

        self.position_open = False
        self.order_in_progress = False
        self.direction = "LONG"
        self.entry_price: float | None = None
        self.take_profit_price: float | None = None
        self.stop_loss_price: float | None = None

        self.safety_orders_used = 0
        self.total_qty = 0.0
        self.total_cost = 0.0
        self.average_price = 0.0
        self.last_order_usdt = 0.0
        self._safety_order_in_progress = False

        self.break_even_armed = False
        self.break_even_price = 0.0

        self._futures_leverage = None
        self._futures_margin_mode = None
        self._last_position_sync = 0.0
        self._pending_strategy_settings: StrategySettings | None = None
        self._last_close_timestamp = 0.0
        self._last_close_price = 0.0
        self.needs_resync = False


    def _notify_runtime_update(self) -> None:
        if self._on_runtime_update is not None:
            self._on_runtime_update(self.pair_name)

    def get_runtime_state(self) -> dict[str, float | int | bool | str]:
        return {
            "is_running": self.running,
            "position_open": self.position_open,
            "direction": self.direction,
            "average_price": self.average_price,
            "total_qty": self.total_qty,
            "total_cost": self.total_cost,
            "safety_orders_used": self.safety_orders_used,
            "take_profit_price": float(self.take_profit_price or 0.0),
            "break_even_armed": self.break_even_armed,
            "break_even_price": self.break_even_price,
            "entry_price": float(self.entry_price or 0.0),
            "last_entry_time": self._last_close_timestamp,
            "cooldown_until": self._last_close_timestamp + (self.strategy_settings.cooldown_minutes * 60.0),
            "last_known_price": 0.0,
            "needs_resync": self.needs_resync,
        }

    def apply_runtime_state(self, runtime: dict[str, object]) -> None:
        self.running = bool(runtime.get("is_running", False))
        self.position_open = bool(runtime.get("position_open", False))
        self.direction = str(runtime.get("direction", self.direction) or self.direction).upper()
        self.average_price = float(runtime.get("average_price", 0.0) or 0.0)
        self.total_qty = float(runtime.get("total_qty", 0.0) or 0.0)
        self.total_cost = float(runtime.get("total_cost", 0.0) or 0.0)
        self.safety_orders_used = int(runtime.get("safety_orders_used", 0) or 0)
        self.take_profit_price = float(runtime.get("take_profit_price", 0.0) or 0.0) or None
        self.break_even_armed = bool(runtime.get("break_even_armed", False))
        self.break_even_price = float(runtime.get("break_even_price", 0.0) or 0.0)
        self.entry_price = float(runtime.get("entry_price", 0.0) or 0.0) or None
        self._last_close_timestamp = float(runtime.get("last_entry_time", 0.0) or 0.0)
        self.needs_resync = True

    def update_settings(self, settings: StrategySettings) -> None:
        if self.position_open:
            self._pending_strategy_settings = settings
            return
        self.strategy_settings = settings
        self.strategy = BaseStrategy(settings)

    async def start(self) -> None:
        self.running = True
        log(f"Pair {self.pair_name} ({self.mode}, {self.exchange_name}) started")
        self._notify_runtime_update()

    async def stop(self) -> None:
        self.running = False
        log(f"Pair {self.pair_name} stop requested")
        self._notify_runtime_update()

    async def run_loop(self) -> None:
        await self.start()
        try:
            while self.running:
                try:
                    self._sync_latest_candles()
                    await self._process_closed_candle_if_needed()
                    await self._process_dca()
                    await self._check_break_even()
                    await self._check_take_profit()
                    await self._periodic_position_sync()

                    latest_price = self.websocket_manager.prices.get(self.pair_name)
                    if latest_price is not None and self.on_price_update is not None:
                        self.on_price_update(self.pair_name, latest_price)
                except Exception as exc:  # noqa: BLE001
                    log(f"Pair loop error {self.pair_name}: {exc}\n{traceback.format_exc()}")

                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            self.running = False
            raise
        except Exception as exc:  # noqa: BLE001
            log(f"Fatal run_loop error {self.pair_name}: {exc}\n{traceback.format_exc()}")
        finally:
            log(f"Pair {self.pair_name} stopped")

    def _sync_latest_candles(self) -> None:
        cache = self.websocket_manager.candles.get(self.pair_name, [])
        if cache:
            self.candles = list(cache[-200:])

    async def _process_closed_candle_if_needed(self) -> None:
        version = self.websocket_manager.candle_versions.get(self.pair_name, 0)
        if version == 0 or version == self._last_candle_version:
            return

        self._last_candle_version = version
        min_len = max(self.strategy_settings.ema_period, self.strategy_settings.rsi_period, self.strategy_settings.adx_period)
        if len(self.candles) < min_len:
            return

        try:
            pandas = importlib.import_module("pandas")
        except ModuleNotFoundError:
            log("pandas is not installed. Install dependencies from requirements.txt")
            return

        df = pandas.DataFrame(
            [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in self.candles]
        )

        _ = self.indicator_engine.calculate_atr(df, self.strategy_settings.adx_period)
        signal = self.strategy.generate_signal(df)
        if signal:
            report_key = "LONG_TEXT" if signal == "LONG" else "SHORT_TEXT"
            report_text = str(self.strategy.last_condition_report.get(report_key, ""))
            log(f"{self.pair_name} {signal} signal | {report_text}")

        if signal == "LONG" and not self.position_open and not self.order_in_progress:
            if self._is_entry_blocked():
                return
            await self._open_initial_position()


    def _is_entry_blocked(self) -> bool:
        now = asyncio.get_running_loop().time()
        cooldown_sec = max(0.0, self.strategy_settings.cooldown_minutes * 60.0)
        if cooldown_sec > 0 and (now - self._last_close_timestamp) < cooldown_sec:
            log(f"Cooldown active, skipping entry: {self.pair_name}")
            return True

        price = self.websocket_manager.prices.get(self.pair_name)
        if self._last_close_price > 0 and price is not None:
            delta_pct = abs(price - self._last_close_price) / self._last_close_price * 100.0
            if delta_pct < self.strategy_settings.anti_reentry_threshold_pct:
                log(f"Anti re-entry active, skipping entry: {self.pair_name}")
                return True
        return False

    async def _open_initial_position(self) -> None:
        if self.position_open or self.order_in_progress:
            return
        if self.strategy_settings.run_mode == "Backtest":
            return

        if self._is_futures_mode():
            await self._ensure_futures_config()
            self.direction = self.strategy_settings.futures_position_side.upper()
        else:
            self.direction = "LONG"

        current_exposure = self._exposure_provider() if self._exposure_provider is not None else 0.0
        base_usdt = await self.order_manager.calculate_entry_size_usdt(
            self.exchange,
            self.pair_name,
            self.strategy_settings,
            is_futures=self._is_futures_mode(),
            leverage=self.strategy_settings.leverage if self._is_futures_mode() else 1,
            current_exposure_usdt=current_exposure,
        )
        if base_usdt is None:
            return

        await self._open_order_with_usdt(base_usdt)

    def _is_futures_mode(self) -> bool:
        return self.strategy_settings.enable_futures and self.mode.lower() == "futures"

    async def _ensure_futures_config(self) -> None:
        margin_api = "Cross" if self.strategy_settings.margin_mode.lower() == "cross" else "Isolated"
        try:
            if self._futures_margin_mode != margin_api or self._futures_leverage != self.strategy_settings.leverage:
                await self.order_manager.configure_futures(
                    self.exchange,
                    self.pair_name,
                    leverage=self.strategy_settings.leverage,
                    margin_mode=margin_api,
                )
                self._futures_margin_mode = margin_api
                self._futures_leverage = self.strategy_settings.leverage
                log(
                    f"Futures config applied {self.pair_name}: leverage={self.strategy_settings.leverage} margin={margin_api}"
                )
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to configure futures for {self.pair_name}: {exc}")

    async def _open_order_with_usdt(self, usdt_amount: float) -> None:
        if self.order_in_progress:
            return
        self.order_in_progress = True
        self.last_order_usdt = usdt_amount
        try:
            if self.strategy_settings.run_mode == "Paper":
                current_price = self.websocket_manager.prices.get(self.pair_name)
                if current_price is None or current_price <= 0:
                    return
                qty = usdt_amount / current_price
                price = current_price
                log(f"Paper order filled: {self.pair_name} qty={qty:.6f} price={price:.6f}")
            elif self._is_futures_mode():
                result = await self.order_manager.open_position_futures(
                    exchange=self.exchange,
                    symbol=self.pair_name,
                    direction_long_short=self.direction,
                    usdt_amount=usdt_amount,
                    use_market=self.strategy_settings.use_market_order,
                    timeout_sec=self.strategy_settings.order_timeout_sec,
                )
                if not isinstance(result, dict):
                    return
                qty = float(result["qty"])
                price = float(result["entry_price"])
            else:
                result = await self.order_manager.open_position_spot(
                    exchange=self.exchange,
                    pair=self.pair_name,
                    side="BUY",
                    amount=usdt_amount,
                    use_market=self.strategy_settings.use_market_order,
                    timeout_sec=self.strategy_settings.order_timeout_sec,
                )
                if not isinstance(result, dict):
                    return
                qty = float(result["quantity"])
                price = float(result["entry_price"])

            commission = (self.strategy_settings.commission_pct / 100.0) * qty * price
            self.position_open = True
            self.entry_price = price if self.entry_price is None else self.entry_price
            self.total_qty += qty
            self.total_cost += qty * price + commission
            self.average_price = self.total_cost / self.total_qty
            self._recalculate_tp()
            self._recalculate_sl()
            self.break_even_price = self.average_price
            if self._is_futures_mode() and self.strategy_settings.protection_orders_on_exchange:
                await self.refresh_protection_orders()
            self._notify_runtime_update()
        finally:
            self.order_in_progress = False

    def _recalculate_sl(self) -> None:
        self.stop_loss_price = (
            self.average_price * (1 - self.strategy_settings.stop_loss_pct / 100.0)
            if self.direction == "LONG"
            else self.average_price * (1 + self.strategy_settings.stop_loss_pct / 100.0)
        )

    def _is_sl_active(self) -> bool:
        mode = self.strategy_settings.stop_loss_mode
        log(f"SL mode: {mode}")
        if mode == "Off":
            return False
        if mode == "Always":
            return True
        if mode == "After Last Safety":
            active = self.safety_orders_used >= self.strategy_settings.safety_orders_count
            if not active:
                log("SL not active yet (safety remaining)")
            return active
        return False

    async def refresh_protection_orders(self) -> None:
        if not self._is_futures_mode() or not self.position_open:
            return
        self._recalculate_tp()
        sl_active = self._is_sl_active()
        self._recalculate_sl()
        await self.order_manager.set_futures_protection(
            exchange=self.exchange,
            symbol=self.pair_name,
            direction=self.direction,
            qty=self.total_qty,
            tp_price=float(self.take_profit_price or 0.0),
            sl_enabled=sl_active,
            sl_price_or_none=self.stop_loss_price if sl_active else None,
            protection_enabled=self.strategy_settings.protection_orders_on_exchange,
        )
        if self.strategy_settings.stop_loss_mode == "After Last Safety" and sl_active:
            log(f"Emergency SL activated (last safety used). SL set at {float(self.stop_loss_price or 0.0):.6f}")
        log("Protection refreshed")

    async def cancel_protection_orders(self) -> None:
        if not self._is_futures_mode():
            return
        await self.order_manager.cancel_futures_protection(self.exchange, self.pair_name)

    async def _process_dca(self) -> None:
        if not self.position_open or self._safety_order_in_progress or self.order_in_progress:
            return
        if self.safety_orders_used >= self.strategy_settings.safety_orders_count:
            return

        price = self.websocket_manager.prices.get(self.pair_name)
        if price is None or self.average_price <= 0:
            return

        step = self.strategy_settings.safety_step_pct / 100.0
        should_place = price <= self.average_price * (1 - step) if self.direction == "LONG" else price >= self.average_price * (1 + step)

        if not should_place:
            return

        self._safety_order_in_progress = True
        try:
            safety_usdt = self.last_order_usdt * self.strategy_settings.volume_multiplier
            await self._open_order_with_usdt(safety_usdt)
            if not self.position_open:
                return

            self.last_order_usdt = safety_usdt
            self.safety_orders_used += 1
            self.break_even_price = self.average_price
            log(f"Safety order placed: {self.pair_name} #{self.safety_orders_used}")
            log(f"New average price: {self.average_price:.6f}")
            log(f"New TP: {self.take_profit_price:.6f}")
            if (
                self._is_futures_mode()
                and self.strategy_settings.protection_orders_on_exchange
                and self.strategy_settings.stop_loss_mode == "After Last Safety"
                and self.safety_orders_used >= self.strategy_settings.safety_orders_count
            ):
                self._recalculate_sl()
                log(f"Emergency SL activated (last safety used). SL set at {float(self.stop_loss_price or 0.0):.6f}")
            if self._is_futures_mode() and self.strategy_settings.protection_orders_on_exchange:
                await self.refresh_protection_orders()
            self._notify_runtime_update()
        finally:
            self._safety_order_in_progress = False

    async def _check_break_even(self) -> None:
        if not self._is_futures_mode() or not self.position_open:
            return

        price = self.websocket_manager.prices.get(self.pair_name)
        if price is None:
            return

        if not self.break_even_armed:
            profit_pct = (price - self.average_price) / self.average_price * 100 if self.direction == "LONG" else (self.average_price - price) / self.average_price * 100
            if profit_pct >= self.strategy_settings.break_even_after_percent:
                self.break_even_armed = True
                self.break_even_price = self.average_price
                log(f"Break-even armed at {self.strategy_settings.break_even_after_percent}% for {self.pair_name}")
                return

        if self.break_even_armed:
            if self.direction == "LONG" and price <= self.break_even_price:
                log("Break-even triggered, closing position")
                await self._close_position("BREAK_EVEN")
            elif self.direction == "SHORT" and price >= self.break_even_price:
                log("Break-even triggered, closing position")
                await self._close_position("BREAK_EVEN")

    async def _check_take_profit(self) -> None:
        if not self.position_open or self.take_profit_price is None:
            return

        price = self.websocket_manager.prices.get(self.pair_name)
        if price is None:
            return

        if self.direction == "LONG" and price >= self.take_profit_price:
            await self._close_position("TP")
        elif self.direction == "SHORT" and price <= self.take_profit_price:
            await self._close_position("TP")

    async def _periodic_position_sync(self) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_position_sync < 30:
            return
        self._last_position_sync = now

        try:
            position = await self.exchange.get_position(
                market_type="futures" if self._is_futures_mode() else "spot",
                symbol=self.pair_name,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"Position sync failed {self.pair_name}: {exc}")
            return

        real_qty = abs(float(position.get("positionAmt", 0.0) or 0.0))
        if self.position_open and real_qty == 0.0:
            log(f"Warning: local position exists, but exchange has none for {self.pair_name}. Resetting state")
            self._reset_position_state()
            self._notify_runtime_update()
            return

        if self.position_open and self._is_futures_mode() and abs(real_qty - self.total_qty) > 1e-6:
            entry = float(position.get("entryPrice", 0.0) or self.average_price)
            self.total_qty = real_qty
            self.average_price = entry
            self.total_cost = self.average_price * self.total_qty
            self._recalculate_tp()
            log("Position resynced")
            self._notify_runtime_update()

    async def cancel_active_order(self) -> None:
        await self.order_manager.cancel_open_order(self.exchange, self.pair_name)

    async def cancel_all_orders(self) -> None:
        try:
            await self.order_manager.cancel_all_orders_for_pair(self.exchange, self.pair_name, self.mode)
        except Exception as exc:  # noqa: BLE001
            log(f"Cancel all orders failed for {self.pair_name}: {exc}\n{traceback.format_exc()}")

    async def close_position_now(self) -> None:
        try:
            closed = await self.order_manager.close_position_now(
                self.exchange,
                self.pair_name,
                self.mode,
                self.direction,
            )
            if not closed:
                log("No open position")
                return
            self.on_trade_closed(self.pair_name, 0.0, self.mode, self.direction)
            self._last_close_timestamp = asyncio.get_running_loop().time()
            self._last_close_price = self.websocket_manager.prices.get(self.pair_name, 0.0)
            self._reset_position_state()
            self._notify_runtime_update()
        except Exception as exc:  # noqa: BLE001
            log(f"Manual close failed for {self.pair_name}: {exc}\n{traceback.format_exc()}")

    async def _close_position(self, reason: str) -> None:
        if self.strategy_settings.run_mode == "Paper":
            paper_price = self.websocket_manager.prices.get(self.pair_name)
            if paper_price is None:
                return
            close_result = {"exit_price": paper_price, "quantity": self.total_qty}
            log(f"Paper position closed: {self.pair_name} reason={reason}")
        elif self._is_futures_mode():
            await self.cancel_protection_orders()
            close_result = await self.order_manager.close_position_futures(self.exchange, self.pair_name)
        else:
            close_result = await self.order_manager.close_position_spot(self.exchange, self.pair_name, self.total_qty)
        if not close_result:
            return

        exit_price = float(close_result["exit_price"])
        qty = float(close_result["quantity"])
        exit_commission = (self.strategy_settings.commission_pct / 100.0) * qty * exit_price

        gross = exit_price * qty if self.direction == "LONG" else (2 * self.average_price - exit_price) * qty
        pnl = (gross - exit_commission) - self.total_cost
        log(f"Position closed {self.pair_name} ({reason}). Profit/Loss: {pnl:.6f}")
        self.on_trade_closed(self.pair_name, pnl, self.mode, self.direction)
        self._last_close_timestamp = asyncio.get_running_loop().time()
        self._last_close_price = exit_price
        self._reset_position_state()
        if self._pending_strategy_settings is not None:
            self.strategy_settings = self._pending_strategy_settings
            self.strategy = BaseStrategy(self.strategy_settings)
            self._pending_strategy_settings = None
            log(f"Strategy updated for {self.pair_name}")

    def _recalculate_tp(self) -> None:
        self.take_profit_price = self.average_price * (1 + self.strategy_settings.take_profit_pct / 100.0) if self.direction == "LONG" else self.average_price * (1 - self.strategy_settings.take_profit_pct / 100.0)

    def _reset_position_state(self) -> None:
        self.position_open = False
        self.order_in_progress = False
        self.entry_price = None
        self.take_profit_price = None
        self.stop_loss_price = None
        self.safety_orders_used = 0
        self.total_qty = 0.0
        self.total_cost = 0.0
        self.average_price = 0.0
        self.last_order_usdt = 0.0
        self._safety_order_in_progress = False
        self.break_even_armed = False
        self.break_even_price = 0.0
