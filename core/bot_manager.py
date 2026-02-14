"""Bot manager that coordinates pair workers, persistence, and asyncio tasks."""

from __future__ import annotations

import asyncio
import traceback
from copy import deepcopy
from dataclasses import asdict
from typing import Any
from collections.abc import Callable

from core.backtest_engine import BacktestEngine
from core.optimizer import StrategyOptimizer
from core.order_manager import OrderManager
from core.pair_manager import PairWorker
from core.risk_manager import RiskManager
from core.state_store import StateStore
from core.websocket_manager import WebSocketManager
from exchanges.base_exchange import BaseExchange
from exchanges.binance_exchange import BinanceExchange
from exchanges.bybit_exchange import BybitExchange
from exchanges.htx_exchange import HtxExchange
from exchanges.mexc_exchange import MexcExchange
from strategy.base_strategy import StrategySettings
from utils.logger import log


class BotManager:
    """Keeps active pair workers and controls their lifecycle."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.pairs: dict[str, PairWorker] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.websocket_manager = WebSocketManager()
        self.order_manager = OrderManager(self.websocket_manager.prices)
        self.risk_manager = RiskManager()
        self.backtest_engine = BacktestEngine()
        self.optimizer = StrategyOptimizer()
        self.strategy_settings = StrategySettings()
        self.pair_settings: dict[str, StrategySettings] = {}
        self._price_callback: Callable[[str, float], None] | None = None
        self.statistics: dict[str, dict[str, float | int | str]] = {}
        self.background_tasks: set[asyncio.Task] = set()
        self.max_active_pairs_warning = 15

        self.state_store = StateStore("bot_state.db")
        self._state_runtime_dirty: set[str] = set()
        self._state_flush_task: asyncio.Task | None = None
        self._runtime_snapshot_task: asyncio.Task | None = None

        self.credentials: dict[str, dict[str, str]] = {
            "Binance": {"key": "", "secret": ""},
            "Bybit": {"key": "", "secret": ""},
            "MEXC": {"key": "", "secret": ""},
            "HTX": {"key": "", "secret": ""},
        }
        self.exchanges: dict[str, BaseExchange] = {}

    async def initialize(self) -> None:
        """Load state from disk and restore in-memory workers."""
        try:
            await asyncio.to_thread(self.state_store.init_db)
            app_state = await asyncio.to_thread(self.state_store.load_app_state)
            if app_state:
                self.strategy_settings.auto_resume_running_pairs = bool(
                    app_state.get("auto_resume_running_pairs", False)
                )

                credentials = app_state.get("credentials")
                if isinstance(credentials, dict):
                    for name in self.credentials:
                        row = credentials.get(name)
                        if isinstance(row, dict):
                            self.credentials[name] = {
                                "key": str(row.get("key", "")),
                                "secret": str(row.get("secret", "")),
                            }

            rows = await asyncio.to_thread(self.state_store.load_all_pairs)
            log(f"Loaded {len(rows)} pairs from state")
            for pair_id, config_json, runtime_json in rows:
                await self._restore_pair_from_state(pair_id, config_json, runtime_json)

            self._runtime_snapshot_task = self.loop.create_task(self._periodic_runtime_snapshot())
        except Exception as exc:  # noqa: BLE001
            log(f"State load error: {exc}\n{traceback.format_exc()}")

    async def _restore_pair_from_state(
        self,
        pair_id: str,
        config_json: dict[str, Any],
        runtime_json: dict[str, Any],
    ) -> None:
        pair_name = pair_id.upper()
        settings = StrategySettings(**{k: v for k, v in config_json.items() if k in StrategySettings.__annotations__})
        mode = str(config_json.get("mode", settings.mode or "Spot"))
        exchange_name = str(config_json.get("exchange_name", "Binance"))

        self.pair_settings[pair_name] = deepcopy(settings)
        worker = self.add_pair(pair_name, mode, exchange_name)
        worker.apply_runtime_state(runtime_json)

        if settings.run_mode == "Live":
            await self.resync_pair_with_exchange(pair_name)

        if settings.auto_resume_running_pairs and bool(runtime_json.get("is_running", False)):
            await self.start_pair(pair_name)

    def set_price_callback(self, callback: Callable[[str, float], None]) -> None:
        self._price_callback = callback

    def set_exchange_credentials(self, exchange_name: str, api_key: str, secret: str) -> None:
        self.credentials[exchange_name] = {"key": api_key, "secret": secret}
        if exchange_name in self.exchanges:
            del self.exchanges[exchange_name]
        self._spawn_background(self._save_app_state())
        log(f"Credentials updated for {exchange_name}")

    async def check_exchange_connection(self, exchange_name: str) -> bool:
        exchange = self._get_exchange(exchange_name)
        if exchange_name != "Binance":
            log(f"{exchange_name} not implemented yet")
            return False
        return await exchange.check_connection()

    def _spawn_background(self, coro: object) -> None:
        task = self.loop.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(lambda t: self.background_tasks.discard(t))

    def _task_done_callback(self, pair: str, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            log(f"Pair task crashed {pair}: {exc}\n{traceback.format_exc()}")

    def update_strategy_settings(self, settings: StrategySettings) -> None:
        self.strategy_settings = deepcopy(settings)
        self._spawn_background(self._save_app_state())
        log("Default strategy settings updated")

    def get_pair_strategy_settings(self, pair_name: str) -> StrategySettings:
        normalized = pair_name.upper()
        if normalized in self.pair_settings:
            return deepcopy(self.pair_settings[normalized])
        return deepcopy(self.strategy_settings)

    def update_pair_strategy_settings(self, pair_name: str, settings: StrategySettings) -> None:
        normalized = pair_name.upper()
        self.pair_settings[normalized] = deepcopy(settings)
        worker = self.pairs.get(normalized)
        if worker is not None:
            worker.mode = settings.mode
            worker.update_settings(deepcopy(settings))
        self._spawn_background(self._save_pair_config(normalized))
        self._spawn_background(self._save_app_state())
        log(f"Strategy updated for {normalized}")

    def _ensure_statistics(
        self,
        pair: str,
        mode: str = "Spot",
        direction: str = "LONG",
        exchange: str = "Binance",
    ) -> None:
        if pair not in self.statistics:
            self.statistics[pair] = {
                "exchange": exchange,
                "mode": mode,
                "direction": direction,
                "trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "pnl_usdt": 0.0,
                "max_drawdown": "TODO",
            }

    def record_trade(self, pair: str, pnl: float, mode: str, direction: str) -> None:
        self._ensure_statistics(pair, mode=mode, direction=direction)
        stats = self.statistics[pair]
        stats["mode"] = mode
        stats["direction"] = direction
        stats["trades"] = int(stats["trades"]) + 1
        if pnl >= 0:
            stats["win_trades"] = int(stats["win_trades"]) + 1
        else:
            stats["loss_trades"] = int(stats["loss_trades"]) + 1
        stats["pnl_usdt"] = float(stats["pnl_usdt"]) + pnl

        log(f"Trade result {pair}: PnL={pnl:.4f}")
        self.schedule_runtime_save(pair)
        if self.risk_manager.register_trade_result(pnl):
            log("Risk rule triggered: 3 consecutive losses, stopping all pairs")
            self._spawn_background(self.stop_all_pairs())

    def _get_exchange(self, exchange_name: str) -> BaseExchange:
        if exchange_name in self.exchanges:
            return self.exchanges[exchange_name]

        creds = self.credentials.get(exchange_name, {"key": "", "secret": ""})
        key = creds.get("key", "")
        secret = creds.get("secret", "")

        if exchange_name == "Binance":
            exchange = BinanceExchange(api_key=key, secret=secret)
        elif exchange_name == "Bybit":
            exchange = BybitExchange(api_key=key, secret=secret)
        elif exchange_name == "MEXC":
            exchange = MexcExchange(api_key=key, secret=secret)
        else:
            exchange = HtxExchange(api_key=key, secret=secret)

        self.exchanges[exchange_name] = exchange
        return exchange

    async def run_backtest(
        self,
        pair: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        settings: StrategySettings,
    ) -> tuple[dict[str, float | int], list[float]]:
        await self.backtest_engine.load_historical_data(pair, timeframe, start_date, end_date)
        report = self.backtest_engine.run_backtest(settings)
        return report, list(self.backtest_engine.equity_curve)

    async def run_optimization(
        self,
        pair: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        parameter_ranges: dict[str, list[float | int]],
        base_settings: StrategySettings,
    ) -> list[dict[str, float | int | dict]]:
        return await self.optimizer.run_grid_search(
            symbol=pair,
            timeframe=timeframe,
            date_range=(start_date, end_date),
            parameter_ranges=parameter_ranges,
            base_settings=base_settings,
        )

    async def stop_all_pairs(self) -> None:
        for pair_name in list(self.tasks.keys()):
            await self.stop_pair(pair_name)

    async def emergency_stop(self) -> None:
        """Global emergency stop: stop pairs + cancel open orders."""
        log("Emergency stop activated")
        for worker in list(self.pairs.values()):
            await worker.cancel_active_order()
        await self.stop_all_pairs()

    def get_total_open_exposure_usdt(self) -> float:
        total = 0.0
        for worker in self.pairs.values():
            if worker.position_open:
                total += float(worker.total_cost)
        return total

    def add_pair(self, pair_name: str, mode: str, exchange_name: str) -> PairWorker:
        normalized = pair_name.upper()
        if normalized not in self.pairs:
            self._ensure_statistics(normalized, mode=mode, exchange=exchange_name)
            exchange = self._get_exchange(exchange_name)
            pair_settings = self.get_pair_strategy_settings(normalized)
            pair_settings.mode = mode
            if mode.lower() == "futures":
                pair_settings.enable_futures = True
            self.pair_settings[normalized] = deepcopy(pair_settings)
            self.pairs[normalized] = PairWorker(
                normalized,
                mode,
                exchange_name,
                exchange,
                self.websocket_manager,
                self.order_manager,
                pair_settings,
                self.record_trade,
                self._price_callback,
                self.get_total_open_exposure_usdt,
                self.schedule_runtime_save,
            )
            if exchange_name == "Binance":
                self._spawn_background(
                    self.websocket_manager.subscribe(normalized, timeframe=pair_settings.timeframe)
                )
            self._spawn_background(self._save_pair_config(normalized))
            self.schedule_runtime_save(normalized)
            log(f"Pair {normalized} added ({mode}, {exchange_name})")
        return self.pairs[normalized]

    async def remove_pair(self, pair_name: str) -> None:
        normalized = pair_name.upper()
        await self.stop_pair(normalized)
        if normalized in self.pairs:
            worker = self.pairs[normalized]
            del self.pairs[normalized]
            self.pair_settings.pop(normalized, None)
            if worker.exchange_name == "Binance":
                await self.websocket_manager.unsubscribe(normalized)
            await asyncio.to_thread(self.state_store.delete_pair, normalized)
            log(f"Pair {normalized} removed")

    async def cancel_pair_orders(self, pair_name: str) -> None:
        normalized = pair_name.upper()
        worker = self.pairs.get(normalized)
        if worker is None:
            log(f"Pair {normalized} not found")
            return
        await worker.cancel_all_orders()

    async def close_pair_now(self, pair_name: str) -> None:
        normalized = pair_name.upper()
        worker = self.pairs.get(normalized)
        if worker is None:
            log(f"Pair {normalized} not found")
            return
        await worker.close_position_now()

    async def close_all_positions_now(self) -> None:
        for pair_name in list(self.pairs.keys()):
            await self.close_pair_now(pair_name)

    async def refresh_pair_protection(self, pair_name: str) -> None:
        worker = self.pairs.get(pair_name.upper())
        if worker is None:
            return
        await worker.refresh_protection_orders()

    async def cancel_pair_protection(self, pair_name: str) -> None:
        worker = self.pairs.get(pair_name.upper())
        if worker is None:
            return
        await worker.cancel_protection_orders()

    async def start_pair(self, pair_name: str) -> None:
        normalized = pair_name.upper()
        worker = self.pairs.get(normalized)
        if worker is None:
            log(f"Cannot start pair {normalized}: not found")
            return

        if worker.exchange_name != "Binance":
            log(f"{worker.exchange_name} not implemented yet")
            return
        if worker.strategy_settings.run_mode == "Backtest":
            log(f"Pair {normalized} is in Backtest mode. Use Statistics tab to run backtest")
            return

        task = self.tasks.get(normalized)
        if task and not task.done():
            log(f"Pair {normalized} already running")
            return

        self.tasks[normalized] = asyncio.create_task(worker.run_loop(), name=f"pair:{normalized}")
        self.tasks[normalized].add_done_callback(lambda t, p=normalized: self._task_done_callback(p, t))

        active = len([t for t in self.tasks.values() if not t.done()])
        if active > self.max_active_pairs_warning:
            log(f"Warning: high load - {active} active pairs")

        self.schedule_runtime_save(normalized)
        log(f"Pair task created for {normalized}")

    async def stop_pair(self, pair_name: str) -> None:
        normalized = pair_name.upper()
        worker = self.pairs.get(normalized)
        task = self.tasks.get(normalized)
        if worker is not None:
            await worker.stop()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.tasks.pop(normalized, None)
            log(f"Pair task cancelled for {normalized}")
        self.schedule_runtime_save(normalized)

    def schedule_runtime_save(self, pair_name: str) -> None:
        normalized = pair_name.upper()
        self._state_runtime_dirty.add(normalized)
        if self._state_flush_task is None or self._state_flush_task.done():
            self._state_flush_task = self.loop.create_task(self._flush_runtime_state_debounced())

    async def _flush_runtime_state_debounced(self) -> None:
        await asyncio.sleep(1.0)
        dirty = set(self._state_runtime_dirty)
        self._state_runtime_dirty.clear()
        for pair_name in dirty:
            await self._save_pair_runtime(pair_name)

    async def _save_pair_config(self, pair_name: str) -> None:
        worker = self.pairs.get(pair_name)
        settings = self.pair_settings.get(pair_name)
        if worker is None or settings is None:
            return

        config = asdict(settings)
        config.update(
            {
                "pair_name": pair_name,
                "exchange_name": worker.exchange_name,
                "mode": worker.mode,
                "direction": worker.direction,
            }
        )
        try:
            await asyncio.to_thread(self.state_store.save_pair_config, pair_name, config)
            log(f"State saved for {pair_name}")
        except Exception as exc:  # noqa: BLE001
            log(f"State save error for {pair_name}: {exc}")

    async def _save_pair_runtime(self, pair_name: str) -> None:
        worker = self.pairs.get(pair_name)
        if worker is None:
            return
        runtime = worker.get_runtime_state()
        runtime["is_running"] = bool(pair_name in self.tasks and not self.tasks[pair_name].done())
        runtime["last_known_price"] = float(self.websocket_manager.prices.get(pair_name, 0.0) or 0.0)
        try:
            await asyncio.to_thread(self.state_store.save_pair_runtime, pair_name, runtime)
            log(f"State saved for {pair_name}")
        except Exception as exc:  # noqa: BLE001
            log(f"State save error for {pair_name}: {exc}")

    async def _save_app_state(self) -> None:
        payload = {
            "auto_resume_running_pairs": self.strategy_settings.auto_resume_running_pairs,
            "credentials": self.credentials,
        }
        try:
            await asyncio.to_thread(self.state_store.save_app_state, payload)
        except Exception as exc:  # noqa: BLE001
            log(f"App state save error: {exc}")

    async def _periodic_runtime_snapshot(self) -> None:
        while True:
            try:
                await asyncio.sleep(15)
                for pair_name in list(self.pairs.keys()):
                    self.schedule_runtime_save(pair_name)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                log(f"Runtime snapshot error: {exc}")

    async def resync_pair_with_exchange(self, pair_name: str) -> None:
        normalized = pair_name.upper()
        worker = self.pairs.get(normalized)
        if worker is None or worker.strategy_settings.run_mode != "Live":
            return

        log(f"Resync started for {normalized}")
        try:
            if worker.mode.lower() == "futures":
                position = await worker.exchange.get_position(market_type="futures", symbol=normalized)
                position_amt = abs(float(position.get("positionAmt", 0.0) or 0.0))
                if position_amt > 0:
                    entry_price = float(position.get("entryPrice", 0.0) or 0.0)
                    worker.position_open = True
                    worker.total_qty = position_amt
                    worker.average_price = entry_price
                    worker.total_cost = entry_price * position_amt
                    worker.entry_price = entry_price
                    worker.direction = "LONG" if float(position.get("positionAmt", 0.0) or 0.0) > 0 else "SHORT"
                    worker._recalculate_tp()
                    worker._recalculate_sl()
                    if worker.strategy_settings.protection_orders_on_exchange:
                        await worker.refresh_protection_orders()
                else:
                    if worker.position_open:
                        worker._reset_position_state()
                        log("Resync: no position on exchange, local reset")
            else:
                base_asset = normalized.replace("USDT", "")
                base_balance = float(await worker.exchange.get_balance(base_asset) or 0.0)
                if base_balance > 0:
                    price = float(self.websocket_manager.prices.get(normalized, 0.0) or 0.0)
                    worker.position_open = True
                    worker.total_qty = base_balance
                    worker.average_price = price
                    worker.total_cost = price * base_balance
                    worker.entry_price = price
                    worker.direction = "LONG"
                    worker._recalculate_tp()
                else:
                    if worker.position_open:
                        worker._reset_position_state()
                        log("Resync: no position on exchange, local reset")
        except Exception as exc:  # noqa: BLE001
            log(f"Resync error for {normalized}: {exc}\n{traceback.format_exc()}")
        finally:
            self.schedule_runtime_save(normalized)
            log(f"Resync complete for {normalized}")

    async def shutdown(self) -> None:
        await self.stop_all_pairs()
        if self._runtime_snapshot_task is not None:
            self._runtime_snapshot_task.cancel()
            try:
                await self._runtime_snapshot_task
            except asyncio.CancelledError:
                pass
        for pair_name in list(self.pairs.keys()):
            await self._save_pair_config(pair_name)
            await self._save_pair_runtime(pair_name)
        await self._save_app_state()

        for task in list(self.background_tasks):
            task.cancel()
        self.background_tasks.clear()

        await self.websocket_manager.shutdown()
        for exchange in self.exchanges.values():
            close_method = getattr(exchange, "close", None)
            if close_method is not None:
                await close_method()
        log("Bot manager shutdown complete")
