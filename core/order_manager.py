"""Order manager for Spot/Futures position lifecycle via BaseExchange."""

from __future__ import annotations

import asyncio

from exchanges.base_exchange import BaseExchange
from strategy.base_strategy import StrategySettings
from utils.logger import log


class OrderManager:
    """Handles opening/closing/monitoring spot and futures orders."""

    def __init__(self, price_source: dict[str, float]) -> None:
        self.price_source = price_source
        self.active_orders: dict[str, dict] = {}

    async def configure_futures(self, exchange: BaseExchange, symbol: str, leverage: int, margin_mode: str) -> None:
        margin_api = "CROSSED" if margin_mode.lower() == "cross" else "ISOLATED"
        await exchange.set_margin_type(symbol, margin_api)
        await exchange.set_leverage(symbol, leverage)

    async def calculate_entry_size_usdt(
        self,
        exchange: BaseExchange,
        symbol: str,
        settings: StrategySettings,
        *,
        is_futures: bool,
        leverage: int,
        current_exposure_usdt: float,
    ) -> float | None:
        current_price = self.price_source.get(symbol)
        if current_price is None and hasattr(exchange, "futures_get_mark_price"):
            current_price = await exchange.futures_get_mark_price(symbol)
        if current_price is None or current_price <= 0:
            log(f"Position size skipped for {symbol}: no current price")
            return None

        balance = await exchange.get_balance("USDT")
        if balance is None or balance <= 0:
            log(f"Position size skipped for {symbol}: balance unavailable")
            return None

        max_exposure_usdt = balance * (settings.max_total_exposure_pct / 100.0)

        if settings.position_size_mode == "Risk-based":
            risk_amount = balance * (settings.risk_per_trade_pct / 100.0)
            stop_distance = max(current_price * (settings.safety_step_pct / 100.0), current_price * 0.001)
            position_qty = risk_amount / max(stop_distance, 1e-9)
            base_notional = position_qty * current_price
            notional_usdt = base_notional * max(leverage, 1) if is_futures else base_notional

            log(
                "Position size calculated:\n"
                f"Balance: {balance:.2f} USDT\n"
                f"Risk: {settings.risk_per_trade_pct:.2f}%\n"
                f"Position size: {notional_usdt:.2f} USDT\n"
                f"Leverage: {max(leverage, 1)}x"
            )
        else:
            notional_usdt = settings.base_order_size_usdt

        if current_exposure_usdt + notional_usdt > max_exposure_usdt:
            log("Max exposure reached")
            return None

        return float(notional_usdt)

    async def open_position_spot(
        self,
        exchange: BaseExchange,
        pair: str,
        side: str,
        amount: float,
        use_market: bool,
        timeout_sec: int = 30,
    ) -> dict | None:
        current_price = self.price_source.get(pair)
        if current_price is None:
            log(f"Open spot skipped for {pair}: no current price")
            return None

        quantity = round(amount / current_price, 6)
        if quantity <= 0:
            return None

        order_type = "MARKET" if use_market else "LIMIT"
        try:
            order = await exchange.place_order(
                market_type="spot",
                symbol=pair,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=current_price if not use_market else None,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to place spot order for {pair}: {exc}")
            return None

        order_id = int(order.get("orderId", 0))
        if not order_id:
            return None

        self.active_orders[pair] = {
            "market_type": "spot",
            "symbol": pair,
            "order_id": order_id,
            "timeout_sec": timeout_sec,
        }

        if not use_market:
            status = await self.monitor_order_spot(exchange, pair, order_id, timeout_sec=timeout_sec)
            if status != "FILLED":
                log("Order watchdog triggered")
                await self.cancel_open_order(exchange, pair)
                return None

        status_data = await exchange.get_order_status(market_type="spot", symbol=pair, order_id=order_id)
        self.active_orders.pop(pair, None)
        executed_qty = float(status_data.get("executedQty", quantity) or quantity)
        cumm_quote = float(status_data.get("cummulativeQuoteQty", 0.0) or 0.0)
        entry_price = cumm_quote / executed_qty if cumm_quote > 0 and executed_qty > 0 else current_price

        return {"pair": pair, "quantity": executed_qty, "entry_price": entry_price, "order_id": order_id}

    async def close_position_spot(self, exchange: BaseExchange, pair: str, quantity: float) -> dict | None:
        if quantity <= 0:
            return None
        try:
            order = await exchange.place_order(
                market_type="spot", symbol=pair, side="SELL", quantity=quantity, order_type="MARKET"
            )
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to close spot position {pair}: {exc}")
            return None

        order_id = int(order.get("orderId", 0))
        status_data = await exchange.get_order_status(market_type="spot", symbol=pair, order_id=order_id)
        executed_qty = float(status_data.get("executedQty", quantity) or quantity)
        cumm_quote = float(status_data.get("cummulativeQuoteQty", 0.0) or 0.0)
        exit_price = cumm_quote / executed_qty if cumm_quote > 0 and executed_qty > 0 else self.price_source.get(pair, 0.0)
        log(f"Position closed (spot): {pair} exit={exit_price}")
        return {"pair": pair, "exit_price": float(exit_price), "quantity": float(executed_qty)}

    async def open_position_futures(
        self,
        exchange: BaseExchange,
        symbol: str,
        direction_long_short: str,
        usdt_amount: float,
        use_market: bool,
        timeout_sec: int,
    ) -> dict | str | None:
        current_price = self.price_source.get(symbol)
        if current_price is None and hasattr(exchange, "futures_get_mark_price"):
            current_price = await exchange.futures_get_mark_price(symbol)
        if current_price is None or current_price <= 0:
            log(f"Open futures skipped for {symbol}: no current price")
            return None

        qty = round(usdt_amount / current_price, 4)  # TODO: align with exchange LOT_SIZE filters.
        if qty <= 0:
            return None

        side = "BUY" if direction_long_short.upper() == "LONG" else "SELL"
        order_type = "MARKET" if use_market else "LIMIT"

        try:
            order = await exchange.place_order(
                market_type="futures",
                symbol=symbol,
                side=side,
                order_type=order_type,
                qty=qty,
                price=current_price if not use_market else None,
                reduce_only=False,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to place futures order for {symbol}: {exc}")
            return None

        order_id = int(order.get("orderId", 0))
        if not order_id:
            return None

        self.active_orders[symbol] = {
            "market_type": "futures",
            "symbol": symbol,
            "order_id": order_id,
            "timeout_sec": timeout_sec,
        }

        if not use_market:
            status = await self.monitor_order_futures(exchange, symbol, order_id, timeout_sec)
            if status != "FILLED":
                log("Order watchdog triggered")
                await self.cancel_open_order(exchange, symbol)
                return "not_filled"

        order_data = await exchange.get_order_status(market_type="futures", symbol=symbol, order_id=order_id)
        self.active_orders.pop(symbol, None)
        executed_qty = float(order_data.get("executedQty", qty) or qty)
        avg_price = float(order_data.get("avgPrice", 0.0) or 0.0)
        if avg_price <= 0:
            avg_price = current_price

        return {"symbol": symbol, "order_id": order_id, "qty": executed_qty, "entry_price": avg_price, "side": side}

    async def close_position_futures(self, exchange: BaseExchange, symbol: str) -> dict | None:
        pos = await exchange.get_position(market_type="futures", symbol=symbol)
        position_amt = float(pos.get("positionAmt", 0.0) or 0.0)
        if position_amt == 0:
            return None

        qty = abs(position_amt)
        close_side = "SELL" if position_amt > 0 else "BUY"

        try:
            order = await exchange.place_order(
                market_type="futures",
                symbol=symbol,
                side=close_side,
                order_type="MARKET",
                qty=qty,
                reduce_only=True,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to close futures position {symbol}: {exc}")
            return None

        order_id = int(order.get("orderId", 0))
        order_data = await exchange.get_order_status(market_type="futures", symbol=symbol, order_id=order_id)
        avg_price = float(order_data.get("avgPrice", 0.0) or 0.0)
        if avg_price <= 0:
            avg_price = self.price_source.get(symbol, 0.0)

        log(f"Position closed (futures): {symbol} exit={avg_price}")
        return {"symbol": symbol, "exit_price": avg_price, "quantity": qty}

    async def set_futures_protection(
        self,
        exchange: BaseExchange,
        symbol: str,
        direction: str,
        qty: float,
        tp_price: float,
        sl_enabled: bool,
        sl_price_or_none: float | None,
        protection_enabled: bool,
    ) -> None:
        if not protection_enabled:
            return
        if qty <= 0:
            return
        if not hasattr(exchange, "futures_cancel_open_orders"):
            log(f"Protection API not supported for {symbol}")
            return

        close_side = "SELL" if direction.upper() == "LONG" else "BUY"
        try:
            await exchange.futures_cancel_open_orders(symbol)
            await exchange.futures_place_tp(symbol, close_side, qty, tp_price)
            log(f"TP set at {tp_price:.6f}")
            if sl_enabled and sl_price_or_none is not None:
                await exchange.futures_place_sl(symbol, close_side, qty, sl_price_or_none)
                log(f"SL set at {sl_price_or_none:.6f}")
            else:
                log("SL disabled")
        except Exception as exc:  # noqa: BLE001
            log(f"Protection orders error for {symbol}: {exc}")


    async def cancel_all_orders_for_pair(self, exchange: BaseExchange, pair: str, mode: str) -> None:
        log(f"Cancel orders requested for {pair}")
        try:
            if mode.lower() == "futures":
                if hasattr(exchange, "futures_cancel_open_orders"):
                    await exchange.futures_cancel_open_orders(pair)
            else:
                if hasattr(exchange, "spot_cancel_open_orders"):
                    await exchange.spot_cancel_open_orders(pair)
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to cancel all orders for {pair}: {exc}")

    async def close_position_now(self, exchange: BaseExchange, pair: str, mode: str, direction: str) -> bool:
        log(f"Close position requested for {pair}")
        await self.cancel_all_orders_for_pair(exchange, pair, mode)

        if mode.lower() == "futures":
            try:
                pos = await exchange.get_position(market_type="futures", symbol=pair)
                position_amt = float(pos.get("positionAmt", 0.0) or 0.0)
                if position_amt == 0:
                    log("No open futures position")
                    return False

                close_side = "SELL" if position_amt > 0 else "BUY"
                await exchange.place_order(
                    market_type="futures",
                    symbol=pair,
                    side=close_side,
                    order_type="MARKET",
                    qty=abs(position_amt),
                    reduce_only=True,
                )
                log("Position closed successfully")
                log(f"Closed position now for {pair}")
                return True
            except Exception as exc:  # noqa: BLE001
                log(f"Failed to close futures position now for {pair}: {exc}")
                return False

        base_asset = pair.upper().replace("USDT", "")
        try:
            base_balance = await exchange.get_balance(base_asset)
            qty = round(float(base_balance or 0.0), 6)
            if qty <= 0:
                log("No spot position to close")
                return False
            await exchange.place_order(
                market_type="spot",
                symbol=pair,
                side="SELL",
                quantity=qty,
                order_type="MARKET",
            )
            log("Position closed successfully")
            log(f"Closed position now for {pair}")
            return True
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to close spot position now for {pair}: {exc}")
            return False

    async def cancel_futures_protection(self, exchange: BaseExchange, symbol: str) -> None:
        if not hasattr(exchange, "futures_cancel_open_orders"):
            return
        try:
            await exchange.futures_cancel_open_orders(symbol)
            log("Protection cancelled")
        except Exception as exc:  # noqa: BLE001
            log(f"Protection cancel error for {symbol}: {exc}")

    async def cancel_open_order(self, exchange: BaseExchange, symbol: str) -> None:
        info = self.active_orders.get(symbol)
        if not info:
            return
        try:
            await exchange.cancel_order(
                market_type=info["market_type"],
                symbol=info["symbol"],
                order_id=info["order_id"],
            )
            log(f"Order cancelled: {info['order_id']} ({symbol})")
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to cancel order {symbol}: {exc}")
        finally:
            self.active_orders.pop(symbol, None)

    async def cancel_all_open_orders(self, exchange_map: dict[str, BaseExchange]) -> None:
        for symbol, info in list(self.active_orders.items()):
            exchange = exchange_map.get(symbol)
            if exchange is not None:
                await self.cancel_open_order(exchange, symbol)

    async def monitor_order_spot(self, exchange: BaseExchange, pair: str, order_id: int, timeout_sec: int) -> str:
        elapsed = 0
        while elapsed < timeout_sec:
            try:
                status_data = await exchange.get_order_status(market_type="spot", symbol=pair, order_id=order_id)
            except Exception as exc:  # noqa: BLE001
                log(f"Spot order monitor error {pair} #{order_id}: {exc}")
                await asyncio.sleep(1)
                elapsed += 1
                continue
            if status_data.get("status", "UNKNOWN") == "FILLED":
                return "FILLED"
            await asyncio.sleep(1)
            elapsed += 1
        return "TIMEOUT"

    async def monitor_order_futures(self, exchange: BaseExchange, symbol: str, order_id: int, timeout_sec: int) -> str:
        elapsed = 0
        while elapsed < timeout_sec:
            try:
                status_data = await exchange.get_order_status(market_type="futures", symbol=symbol, order_id=order_id)
            except Exception as exc:  # noqa: BLE001
                log(f"Futures order monitor error {symbol} #{order_id}: {exc}")
                await asyncio.sleep(1)
                elapsed += 1
                continue
            if status_data.get("status", "UNKNOWN") == "FILLED":
                return "FILLED"
            await asyncio.sleep(1)
            elapsed += 1
        return "TIMEOUT"
