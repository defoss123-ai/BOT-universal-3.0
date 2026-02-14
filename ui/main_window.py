"""Main window containing all top-level tabs."""

from __future__ import annotations

import asyncio

from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from core.bot_manager import BotManager
from ui.exchanges_tab import ExchangesTab
from ui.logs_tab import LogsTab
from ui.optimizer_tab import OptimizerTab
from ui.pairs_tab import PairsTab
from ui.statistics_tab import StatisticsTab
from ui.strategy_tab import StrategyTab
from utils.logger import log


class MainWindow(QMainWindow):
    """Main application window for the bot skeleton."""

    def __init__(self, bot_manager: BotManager, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.bot_manager = bot_manager
        self.loop = loop

        self.setWindowTitle("Universal Trading Bot (Skeleton)")
        self.resize(1100, 700)

        self.tabs = QTabWidget(self)
        self.setCentralWidget(self.tabs)

        self._build_tabs()
        self._bind_hotkeys()

    def _build_tabs(self) -> None:
        """Initialize and add all tabs to QTabWidget."""
        strategy_tab = StrategyTab()
        pairs_tab = PairsTab(self.bot_manager, self.loop, strategy_tab.get_strategy_settings)
        self.pairs_tab = pairs_tab

        self.bot_manager.set_price_callback(pairs_tab.emit_price_update)

        self.tabs.addTab(pairs_tab, "Pairs")
        self.tabs.addTab(strategy_tab, "Strategy")
        self.tabs.addTab(ExchangesTab(self.bot_manager, self.loop), "Exchanges")
        self.tabs.addTab(StatisticsTab(self.bot_manager, self.loop, strategy_tab.get_strategy_settings), "Statistics")
        self.tabs.addTab(OptimizerTab(self.bot_manager, self.loop, strategy_tab.get_strategy_settings), "Optimizer")
        self.tabs.addTab(LogsTab(), "Logs")

    def _confirm_action(self, message: str) -> bool:
        reply = QMessageBox.question(
            self,
            "Confirm action",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _bind_hotkeys(self) -> None:
        self._hotkey_emergency_stop = QShortcut(QKeySequence("Ctrl+E"), self)
        self._hotkey_emergency_stop.activated.connect(self.trigger_emergency_stop)

        self._hotkey_close_pair = QShortcut(QKeySequence("Ctrl+W"), self)
        self._hotkey_close_pair.activated.connect(self.pairs_tab.trigger_close_position_now)

        self._hotkey_refresh_protection = QShortcut(QKeySequence("Ctrl+R"), self)
        self._hotkey_refresh_protection.activated.connect(self.pairs_tab.trigger_refresh_protection)

        self._hotkey_cancel_orders = QShortcut(QKeySequence("Ctrl+K"), self)
        self._hotkey_cancel_orders.activated.connect(self.pairs_tab.trigger_cancel_orders_for_pair)

    async def _run_emergency_stop(self) -> None:
        await self.bot_manager.emergency_stop()
        log("Action completed: Emergency Stop")

    def trigger_emergency_stop(self) -> None:
        if not self._confirm_action("Are you sure? This will close position at market price."):
            return
        self.loop.create_task(self._run_emergency_stop())

    async def _run_close_all_positions(self) -> None:
        await self.bot_manager.close_all_positions_now()
        log("Action completed: Close All Positions")

    def trigger_close_all_positions(self) -> None:
        if not self._confirm_action("Are you sure? This will close position at market price."):
            return
        self.loop.create_task(self._run_close_all_positions())


    def restore_pairs_from_manager(self) -> None:
        self.pairs_tab.load_pairs_from_manager()
