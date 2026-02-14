"""WebSocket manager for market price and kline streams."""

from __future__ import annotations

import asyncio
import importlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from utils.logger import log


@dataclass
class Candle:
    """OHLCV candle container."""

    open: float
    high: float
    low: float
    close: float
    volume: float


class WebSocketManager:
    """Handles websocket connections and live market caches per exchange."""

    BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"

    def __init__(self) -> None:
        self.connections: dict[str, Any] = {}
        self.listen_tasks: dict[str, asyncio.Task] = {}
        self.prices: dict[str, float] = {}
        self.subscribed_pairs: dict[str, set[str]] = defaultdict(set)
        self.pair_timeframes: dict[str, str] = {}
        self.candles: dict[str, list[Candle]] = defaultdict(list)
        self.candle_versions: dict[str, int] = defaultdict(int)
        self._running = True

    async def connect(self, exchange_name: str) -> None:
        """Start a dedicated websocket listener for one exchange."""
        exchange_key = exchange_name.lower()
        if exchange_key != "binance":
            log(f"WebSocket for {exchange_name} is not implemented yet")
            return

        task = self.listen_tasks.get(exchange_key)
        if task and not task.done():
            return

        self.listen_tasks[exchange_key] = asyncio.create_task(self._listen_binance(), name="ws:binance")
        log("WebSocket listener task created for Binance")

    async def subscribe(self, pair_name: str, timeframe: str = "1m") -> None:
        """Subscribe pair to miniTicker and kline streams."""
        pair = pair_name.upper()
        self.subscribed_pairs["binance"].add(pair)
        self.pair_timeframes[pair] = timeframe
        log(f"Subscribed pair {pair} to Binance stream")

        await self.connect("binance")
        await self._sync_binance_subscriptions()

    async def unsubscribe(self, pair_name: str) -> None:
        """Unsubscribe pair from all Binance streams."""
        pair = pair_name.upper()
        timeframe = self.pair_timeframes.get(pair, "1m")
        if pair in self.subscribed_pairs["binance"]:
            self.subscribed_pairs["binance"].remove(pair)
            self.pair_timeframes.pop(pair, None)
            log(f"Unsubscribed pair {pair} from Binance stream")

        await self._sync_binance_subscriptions(unsubscribe_pair=pair, timeframe=timeframe)

    async def listen(self) -> None:
        """Background keeper loop."""
        while self._running:
            await asyncio.sleep(1)

    async def shutdown(self) -> None:
        """Stop listeners and close active sockets."""
        self._running = False

        for task in list(self.listen_tasks.values()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.listen_tasks.clear()

        for connection in list(self.connections.values()):
            await connection.close()

        self.connections.clear()
        log("WebSocket manager shutdown complete")

    async def _sync_binance_subscriptions(
        self,
        unsubscribe_pair: str | None = None,
        timeframe: str = "1m",
    ) -> None:
        """Send subscribe/unsubscribe payloads to Binance when connected."""
        connection = self.connections.get("binance")
        if connection is None:
            return

        try:
            if unsubscribe_pair is not None:
                await connection.send(
                    json.dumps(
                        {
                            "method": "UNSUBSCRIBE",
                            "params": [
                                f"{unsubscribe_pair.lower()}@miniTicker",
                                f"{unsubscribe_pair.lower()}@kline_{timeframe}",
                            ],
                            "id": 2,
                        }
                    )
                )

            params: list[str] = []
            for pair in sorted(self.subscribed_pairs["binance"]):
                tf = self.pair_timeframes.get(pair, "1m")
                params.append(f"{pair.lower()}@miniTicker")
                params.append(f"{pair.lower()}@kline_{tf}")

            if params:
                await connection.send(
                    json.dumps(
                        {
                            "method": "SUBSCRIBE",
                            "params": params,
                            "id": 1,
                        }
                    )
                )
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to sync Binance subscriptions: {exc}")

    async def _listen_binance(self) -> None:
        """Listen Binance WS and update price/candle caches with reconnect."""
        try:
            websockets_module = importlib.import_module("websockets")
        except ModuleNotFoundError:
            log("WebSocket library is not installed. Install dependencies from requirements.txt")
            return

        while self._running:
            try:
                async with websockets_module.connect(
                    self.BINANCE_WS_URL,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    self.connections["binance"] = ws
                    log("Connected to Binance WebSocket")
                    await self._sync_binance_subscriptions()

                    while self._running:
                        raw_message = await ws.recv()
                        payload: dict[str, Any] = json.loads(raw_message)
                        event_type = payload.get("e")

                        if event_type == "miniTicker":
                            self._handle_miniticker(payload)
                        elif event_type == "kline":
                            self._handle_kline(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log(f"Binance WebSocket error: {exc}. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
            finally:
                self.connections.pop("binance", None)

    def _handle_miniticker(self, payload: dict[str, Any]) -> None:
        symbol = payload.get("s")
        close_price = payload.get("c")
        if symbol and close_price is not None:
            try:
                self.prices[symbol] = float(close_price)
            except (TypeError, ValueError):
                return

    def _handle_kline(self, payload: dict[str, Any]) -> None:
        symbol = payload.get("s")
        kline = payload.get("k", {})
        if not symbol or not kline.get("x"):
            return

        try:
            candle = Candle(
                open=float(kline["o"]),
                high=float(kline["h"]),
                low=float(kline["l"]),
                close=float(kline["c"]),
                volume=float(kline["v"]),
            )
        except (KeyError, TypeError, ValueError):
            return

        data = self.candles[symbol]
        data.append(candle)
        if len(data) > 200:
            del data[0]

        self.candle_versions[symbol] += 1
