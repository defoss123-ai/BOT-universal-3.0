"""Binance Spot + USDT-M Futures REST adapter (aiohttp)."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import os
import time
from urllib.parse import urlencode

from exchanges.base_exchange import BaseExchange
from utils.logger import log


class BinanceExchange(BaseExchange):
    """Binance Spot/Futures API client implementing BaseExchange."""

    def __init__(
        self,
        api_key: str = "",
        secret: str = "",
        spot_base_url: str = "https://api.binance.com",
        futures_base_url: str = "https://fapi.binance.com",
    ) -> None:
        super().__init__(
            api_key=api_key or os.getenv("BINANCE_API_KEY", ""),
            secret=secret or os.getenv("BINANCE_API_SECRET", ""),
        )
        self.spot_base_url = spot_base_url
        self.futures_base_url = futures_base_url
        self.session = None
        self._aiohttp = None

    async def connect(self) -> None:
        if self._aiohttp is None:
            try:
                self._aiohttp = importlib.import_module("aiohttp")
            except ModuleNotFoundError as exc:
                raise RuntimeError("aiohttp is required for Binance REST trading") from exc

        if self.session is None or self.session.closed:
            self.session = self._aiohttp.ClientSession(timeout=self._aiohttp.ClientTimeout(total=15))

    async def check_connection(self) -> bool:
        await self.connect()
        try:
            data = await self._spot_request("GET", "/api/v3/ping")
            return data == {}
        except Exception as exc:  # noqa: BLE001
            log(f"Binance connection check failed: {exc}")
            return False

    async def get_balance(self, asset: str = "USDT") -> float | None:
        data = await self._spot_request("GET", "/api/v3/account", signed=True)
        for row in data.get("balances", []):
            if row.get("asset") == asset:
                return float(row.get("free", 0.0))
        return None

    async def place_order(self, **kwargs) -> dict:
        market_type = kwargs.get("market_type", "spot").lower()
        if market_type == "futures":
            return await self._futures_place_order(
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs.get("order_type", "MARKET"),
                qty=kwargs["qty"],
                price=kwargs.get("price"),
                reduce_only=kwargs.get("reduce_only", False),
            )

        return await self._spot_place_order(
            symbol=kwargs["symbol"],
            side=kwargs["side"],
            quantity=kwargs["quantity"],
            order_type=kwargs.get("order_type", "MARKET"),
            price=kwargs.get("price"),
        )

    async def cancel_order(self, **kwargs) -> dict:
        market_type = kwargs.get("market_type", "spot").lower()
        if market_type == "futures":
            return await self._futures_request(
                "DELETE",
                "/fapi/v1/order",
                params={"symbol": kwargs["symbol"].upper(), "orderId": kwargs["order_id"]},
                signed=True,
            )

        return await self._spot_request(
            "DELETE",
            "/api/v3/order",
            params={"symbol": kwargs["symbol"].upper(), "orderId": kwargs["order_id"]},
            signed=True,
        )

    async def get_order_status(self, **kwargs) -> dict:
        market_type = kwargs.get("market_type", "spot").lower()
        if market_type == "futures":
            return await self._futures_request(
                "GET",
                "/fapi/v1/order",
                params={"symbol": kwargs["symbol"].upper(), "orderId": kwargs["order_id"]},
                signed=True,
            )

        return await self._spot_request(
            "GET",
            "/api/v3/order",
            params={"symbol": kwargs["symbol"].upper(), "orderId": kwargs["order_id"]},
            signed=True,
        )

    async def get_position(self, **kwargs) -> dict:
        market_type = kwargs.get("market_type", "spot").lower()
        symbol = kwargs.get("symbol", "")
        if market_type != "futures":
            return {"entryPrice": 0.0, "positionAmt": 0.0, "unrealizedProfit": 0.0}

        rows = await self._futures_request("GET", "/fapi/v2/positionRisk", signed=True)
        for row in rows:
            if row.get("symbol") == symbol.upper():
                return {
                    "entryPrice": float(row.get("entryPrice", 0.0) or 0.0),
                    "positionAmt": float(row.get("positionAmt", 0.0) or 0.0),
                    "unrealizedProfit": float(row.get("unRealizedProfit", 0.0) or 0.0),
                }
        return {"entryPrice": 0.0, "positionAmt": 0.0, "unrealizedProfit": 0.0}

    async def set_leverage(self, symbol: str, leverage: int) -> dict:
        return await self._futures_request(
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": symbol.upper(), "leverage": leverage},
            signed=True,
        )

    async def set_margin_type(self, symbol: str, margin_type: str) -> dict:
        return await self._futures_request(
            "POST",
            "/fapi/v1/marginType",
            params={"symbol": symbol.upper(), "marginType": margin_type.upper()},
            signed=True,
        )

    async def futures_get_mark_price(self, symbol: str) -> float | None:
        data = await self._futures_request(
            "GET",
            "/fapi/v1/premiumIndex",
            params={"symbol": symbol.upper()},
        )
        try:
            return float(data.get("markPrice"))
        except (TypeError, ValueError):
            return None

    async def futures_place_tp(self, symbol: str, close_side: str, qty: float, tp_price: float) -> dict:
        return await self._futures_request(
            "POST",
            "/fapi/v1/order",
            params={
                "symbol": symbol.upper(),
                "side": close_side.upper(),
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": f"{tp_price:.6f}",
                "closePosition": "false",
                "quantity": f"{qty:.6f}",
                "reduceOnly": "true",
                "workingType": "MARK_PRICE",
            },
            signed=True,
        )

    async def futures_place_sl(self, symbol: str, close_side: str, qty: float, sl_price: float) -> dict:
        return await self._futures_request(
            "POST",
            "/fapi/v1/order",
            params={
                "symbol": symbol.upper(),
                "side": close_side.upper(),
                "type": "STOP_MARKET",
                "stopPrice": f"{sl_price:.6f}",
                "closePosition": "false",
                "quantity": f"{qty:.6f}",
                "reduceOnly": "true",
                "workingType": "MARK_PRICE",
            },
            signed=True,
        )

    async def futures_cancel_open_orders(self, symbol: str) -> dict:
        return await self._futures_request(
            "DELETE",
            "/fapi/v1/allOpenOrders",
            params={"symbol": symbol.upper()},
            signed=True,
        )

    async def spot_cancel_open_orders(self, symbol: str) -> dict:
        return await self._spot_request(
            "DELETE",
            "/api/v3/openOrders",
            params={"symbol": symbol.upper()},
            signed=True,
        )

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def _spot_place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: float | None = None,
    ) -> dict:
        params: dict[str, str | float] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": f"{quantity:.6f}",
        }
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("LIMIT order requires price")
            params["timeInForce"] = "GTC"
            params["price"] = f"{price:.6f}"

        result = await self._spot_request("POST", "/api/v3/order", params=params, signed=True)
        log(f"Order placed: {result.get('orderId')} {symbol} {side} {order_type}")
        return result

    async def _futures_place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: float | None = None,
        reduce_only: bool = False,
    ) -> dict:
        params: dict[str, str | float] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": f"{qty:.6f}",
            "reduceOnly": "true" if reduce_only else "false",
        }
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("LIMIT futures order requires price")
            params["timeInForce"] = "GTC"
            params["price"] = f"{price:.6f}"

        result = await self._futures_request("POST", "/fapi/v1/order", params=params, signed=True)
        log(
            f"Futures order placed: {result.get('orderId')} {symbol} {side} {order_type} reduceOnly={reduce_only}"
        )
        return result

    def _sign(self, query: str) -> str:
        return hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    async def _spot_request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        await self.connect()
        await self.acquire_rate_limit()
        request_params = params.copy() if params else {}
        headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}

        if signed:
            request_params["timestamp"] = int(time.time() * 1000)
            query = urlencode(request_params)
            request_params["signature"] = self._sign(query)

        url = f"{self.spot_base_url}{path}"
        async with self.session.request(method, url, params=request_params, headers=headers) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f"Binance API error {response.status}: {payload}")
            return payload

    async def _futures_request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        await self.connect()
        await self.acquire_rate_limit()
        request_params = params.copy() if params else {}
        headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}

        if signed:
            request_params["timestamp"] = int(time.time() * 1000)
            query = urlencode(request_params)
            request_params["signature"] = self._sign(query)

        url = f"{self.futures_base_url}{path}"
        async with self.session.request(method, url, params=request_params, headers=headers) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                msg = str(payload)
                if "No need to change" in msg:
                    return payload
                raise RuntimeError(f"Binance Futures API error {response.status}: {payload}")
            return payload
