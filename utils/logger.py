"""Simple application logger used by UI and async workers."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

LogListener = Callable[[str], None]

_listeners: list[LogListener] = []


def register_listener(listener: LogListener) -> None:
    """Register callback that receives formatted log messages."""
    if listener not in _listeners:
        _listeners.append(listener)


def unregister_listener(listener: LogListener) -> None:
    """Unregister previously added log callback."""
    if listener in _listeners:
        _listeners.remove(listener)


def log(message: str) -> None:
    """Print message to console and broadcast it to UI listeners."""
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
    print(formatted)
    for listener in list(_listeners):
        listener(formatted)
