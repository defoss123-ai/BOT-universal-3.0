"""Configuration placeholders for the bot application."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppConfig:
    """Global application config placeholder."""

    # TODO: extend with environment, exchange, and strategy settings.
    app_name: str = "Universal Trading Bot"
    version: str = "0.1.0-skeleton"
