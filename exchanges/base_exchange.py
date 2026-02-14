"""Unified exchange interface with simple async rate limiting."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Any


class BaseExchange(ABC):
    """Abstract exchange interface for spot/futures operations."""

    def __init__(
        self,
        api_key: str = "",
        secret: str = "",
        max_requests_per_second: int = 8,
    ) -> None:
        self.api_key = api_key
        self.secret = secret
        self.max_requests_per_second = max_requests_per_second

        self._request_queue: asyncio.Queue[float] = asyncio.Queue()
        self._request_timestamps: deque[float] = deque()
        self._rate_lock = asyncio.Lock()

    async def acquire_rate_limit(self) -> None:
        """Throttle REST calls to max_requests_per_second using queue + time window."""
        await self._request_queue.put(time.monotonic())
        async with self._rate_lock:
            now = time.monotonic()
            while self._request_timestamps and now - self._request_timestamps[0] > 1.0:
                self._request_timestamps.popleft()

            if len(self._request_timestamps) >= self.max_requests_per_second:
                wait_for = 1.0 - (now - self._request_timestamps[0])
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                    now = time.monotonic()
                    while self._request_timestamps and now - self._request_timestamps[0] > 1.0:
                        self._request_timestamps.popleft()

            self._request_timestamps.append(time.monotonic())
            _ = await self._request_queue.get()
            self._request_queue.task_done()

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def check_connection(self) -> bool: ...

    @abstractmethod
    async def get_balance(self, asset: str = "USDT") -> float | None: ...

    @abstractmethod
    async def place_order(self, **kwargs: Any) -> dict: ...

    @abstractmethod
    async def cancel_order(self, **kwargs: Any) -> dict: ...

    @abstractmethod
    async def get_order_status(self, **kwargs: Any) -> dict: ...

    @abstractmethod
    async def get_position(self, **kwargs: Any) -> dict: ...

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> dict: ...

    @abstractmethod
    async def set_margin_type(self, symbol: str, margin_type: str) -> dict: ...
