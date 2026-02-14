"""Pairs management tab UI."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from copy import deepcopy

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.bot_manager import BotManager
from strategy.base_strategy import StrategySettings
from utils.logger import log


class PairStrategyDialog(QDialog):
    """Dialog to edit strategy settings for a single pair."""

    def __init__(self, settings: StrategySettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Pair Strategy")
        self._settings = deepcopy(settings)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.take_profit_input = QLineEdit(str(self._settings.take_profit_pct))
        self.safety_step_input = QLineEdit(str(self._settings.safety_step_pct))
        self.safety_count_input = QLineEdit(str(self._settings.safety_orders_count))
        self.volume_multiplier_input = QLineEdit(str(self._settings.volume_multiplier))

        self.rsi_period_input = QLineEdit(str(self._settings.rsi_period))
        self.rsi_level_input = QLineEdit(str(self._settings.rsi_level))
        self.ema_period_input = QLineEdit(str(self._settings.ema_period))
        self.adx_period_input = QLineEdit(str(self._settings.adx_period))
        self.adx_threshold_input = QLineEdit(str(self._settings.adx_threshold))
        self.volume_spike_multiplier_input = QLineEdit(str(self._settings.volume_spike_multiplier))
        self.atr_min_value_input = QLineEdit(str(self._settings.atr_min_value))
        self.risk_per_trade_input = QLineEdit(str(self._settings.risk_per_trade_pct))
        self.max_total_exposure_input = QLineEdit(str(self._settings.max_total_exposure_pct))

        self.position_size_mode_dropdown = QComboBox()
        self.position_size_mode_dropdown.addItems(["Fixed", "Risk-based"])
        self.position_size_mode_dropdown.setCurrentText(self._settings.position_size_mode)

        self.break_even_input = QLineEdit(str(self._settings.break_even_after_percent))
        self.stop_loss_pct_input = QLineEdit(str(self._settings.stop_loss_pct))
        self.leverage_input = QLineEdit(str(self._settings.leverage))
        self.timeout_input = QLineEdit(str(self._settings.order_timeout_sec))
        self.cooldown_input = QLineEdit(str(self._settings.cooldown_minutes))

        self.margin_dropdown = QComboBox()
        self.margin_dropdown.addItems(["Cross", "Isolated"])
        self.margin_dropdown.setCurrentText(self._settings.margin_mode)

        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems(["Spot", "Futures"])
        self.mode_dropdown.setCurrentText(self._settings.mode)

        self.direction_dropdown = QComboBox()
        self.direction_dropdown.addItems(["Long", "Short"])
        self.direction_dropdown.setCurrentText(self._settings.futures_position_side)

        self.run_mode_dropdown = QComboBox()
        self.run_mode_dropdown.addItems(["Live", "Paper", "Backtest"])
        self.run_mode_dropdown.setCurrentText(self._settings.run_mode)

        self.market_checkbox = QCheckBox("Use Market First Order")
        self.market_checkbox.setChecked(self._settings.use_market_order)
        self.protection_orders_checkbox = QCheckBox("Protection Orders on Exchange")
        self.protection_orders_checkbox.setChecked(self._settings.protection_orders_on_exchange)
        self.stop_loss_mode_dropdown = QComboBox()
        self.stop_loss_mode_dropdown.addItems(["Off", "Always", "After Last Safety"])
        self.stop_loss_mode_dropdown.setCurrentText(self._settings.stop_loss_mode)

        self.use_rsi_checkbox = QCheckBox("Use RSI")
        self.use_rsi_checkbox.setChecked(self._settings.use_rsi)
        self.use_ema_filter_checkbox = QCheckBox("Use EMA Trend Filter")
        self.use_ema_filter_checkbox.setChecked(self._settings.use_ema_trend_filter)
        self.use_adx_filter_checkbox = QCheckBox("Use ADX Filter")
        self.use_adx_filter_checkbox.setChecked(self._settings.use_adx_filter)
        self.use_volume_filter_checkbox = QCheckBox("Use Volume Filter")
        self.use_volume_filter_checkbox.setChecked(self._settings.use_volume_filter)
        self.use_atr_filter_checkbox = QCheckBox("Use ATR Filter")
        self.use_atr_filter_checkbox.setChecked(self._settings.use_atr_filter)

        form.addRow("Take Profit %", self.take_profit_input)
        form.addRow("Safety Step %", self.safety_step_input)
        form.addRow("Safety Orders Count", self.safety_count_input)
        form.addRow("Volume Multiplier", self.volume_multiplier_input)
        form.addRow("RSI Period", self.rsi_period_input)
        form.addRow("RSI Level", self.rsi_level_input)
        form.addRow("EMA Period", self.ema_period_input)
        form.addRow("ADX Period", self.adx_period_input)
        form.addRow("ADX Threshold", self.adx_threshold_input)
        form.addRow("Volume Spike Multiplier", self.volume_spike_multiplier_input)
        form.addRow("ATR Min Value", self.atr_min_value_input)
        form.addRow("Position size mode", self.position_size_mode_dropdown)
        form.addRow("Risk per trade (%)", self.risk_per_trade_input)
        form.addRow("Max total exposure (%)", self.max_total_exposure_input)
        form.addRow("Break-even %", self.break_even_input)
        form.addRow("Stop Loss Mode", self.stop_loss_mode_dropdown)
        form.addRow("Stop Loss %", self.stop_loss_pct_input)
        form.addRow("Leverage", self.leverage_input)
        form.addRow("Margin Type", self.margin_dropdown)
        form.addRow("Mode", self.mode_dropdown)
        form.addRow("Direction", self.direction_dropdown)
        form.addRow("Order timeout (sec)", self.timeout_input)
        form.addRow("Cooldown minutes", self.cooldown_input)
        form.addRow("Run mode", self.run_mode_dropdown)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(self.market_checkbox)
        layout.addWidget(self.protection_orders_checkbox)
        layout.addWidget(self.use_rsi_checkbox)
        layout.addWidget(self.use_ema_filter_checkbox)
        layout.addWidget(self.use_adx_filter_checkbox)
        layout.addWidget(self.use_volume_filter_checkbox)
        layout.addWidget(self.use_atr_filter_checkbox)
        layout.addWidget(buttons)

    def _as_int(self, value: str, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_float(self, value: str, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def get_settings(self) -> StrategySettings:
        updated = deepcopy(self._settings)
        updated.take_profit_pct = self._as_float(self.take_profit_input.text(), updated.take_profit_pct)
        updated.safety_step_pct = self._as_float(self.safety_step_input.text(), updated.safety_step_pct)
        updated.safety_orders_count = self._as_int(self.safety_count_input.text(), updated.safety_orders_count)
        updated.volume_multiplier = self._as_float(self.volume_multiplier_input.text(), updated.volume_multiplier)
        updated.rsi_period = self._as_int(self.rsi_period_input.text(), updated.rsi_period)
        updated.rsi_level = self._as_float(self.rsi_level_input.text(), updated.rsi_level)
        updated.ema_period = self._as_int(self.ema_period_input.text(), updated.ema_period)
        updated.adx_period = self._as_int(self.adx_period_input.text(), updated.adx_period)
        updated.adx_threshold = self._as_float(self.adx_threshold_input.text(), updated.adx_threshold)
        updated.volume_spike_multiplier = self._as_float(
            self.volume_spike_multiplier_input.text(), updated.volume_spike_multiplier
        )
        updated.atr_min_value = self._as_float(self.atr_min_value_input.text(), updated.atr_min_value)
        updated.position_size_mode = self.position_size_mode_dropdown.currentText()
        updated.risk_per_trade_pct = self._as_float(self.risk_per_trade_input.text(), updated.risk_per_trade_pct)
        updated.max_total_exposure_pct = self._as_float(self.max_total_exposure_input.text(), updated.max_total_exposure_pct)
        updated.break_even_after_percent = self._as_float(self.break_even_input.text(), updated.break_even_after_percent)
        updated.stop_loss_pct = self._as_float(self.stop_loss_pct_input.text(), updated.stop_loss_pct)
        updated.leverage = self._as_int(self.leverage_input.text(), updated.leverage)
        updated.margin_mode = self.margin_dropdown.currentText()
        updated.mode = self.mode_dropdown.currentText()
        updated.enable_futures = updated.mode.lower() == "futures"
        updated.futures_position_side = self.direction_dropdown.currentText()
        updated.order_timeout_sec = self._as_int(self.timeout_input.text(), updated.order_timeout_sec)
        updated.cooldown_minutes = self._as_float(self.cooldown_input.text(), updated.cooldown_minutes)
        updated.use_market_order = self.market_checkbox.isChecked()
        updated.protection_orders_on_exchange = self.protection_orders_checkbox.isChecked()
        updated.stop_loss_mode = self.stop_loss_mode_dropdown.currentText()
        updated.enable_stop_loss = updated.stop_loss_mode != "Off"
        updated.run_mode = self.run_mode_dropdown.currentText()
        updated.use_rsi = self.use_rsi_checkbox.isChecked()
        updated.use_ema_trend_filter = self.use_ema_filter_checkbox.isChecked()
        updated.use_adx_filter = self.use_adx_filter_checkbox.isChecked()
        updated.use_volume_filter = self.use_volume_filter_checkbox.isChecked()
        updated.use_atr_filter = self.use_atr_filter_checkbox.isChecked()
        return updated


class AddPairDialog(QDialog):
    """Dialog to add a new pair manually."""

    def __init__(self, default_mode: str, default_exchange: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Pair")
        self._build_ui(default_mode, default_exchange)

    def _build_ui(self, default_mode: str, default_exchange: str) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("BTCUSDT")

        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems(["Spot", "Futures"])
        self.mode_dropdown.setCurrentText(default_mode)

        self.exchange_dropdown = QComboBox()
        self.exchange_dropdown.addItems(["Binance", "Bybit", "MEXC", "HTX"])
        self.exchange_dropdown.setCurrentText(default_exchange)

        form.addRow("Symbol", self.symbol_input)
        form.addRow("Mode", self.mode_dropdown)
        form.addRow("Exchange", self.exchange_dropdown)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def get_values(self) -> tuple[str, str, str]:
        return (
            self.symbol_input.text().strip().upper(),
            self.mode_dropdown.currentText(),
            self.exchange_dropdown.currentText(),
        )




class PairsTab(QWidget):
    """UI tab for managing trading pairs."""

    COL_PAIR = 0
    COL_MODE = 1
    COL_STATUS = 2
    COL_POSITION = 3
    COL_DCA = 4
    COL_PRICE = 5
    COL_EXCHANGE = 6

    price_updated = pyqtSignal(str, float)

    def __init__(
        self,
        bot_manager: BotManager,
        loop: asyncio.AbstractEventLoop,
        get_settings: Callable[[], StrategySettings],
    ) -> None:
        super().__init__()
        self.bot_manager = bot_manager
        self.loop = loop
        self.get_settings = get_settings
        self.selected_pair_id: str | None = None
        self._strategy_dialog: PairStrategyDialog | None = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        button_layout = QHBoxLayout()
        self.exchange_selector = QComboBox()
        self.exchange_selector.addItems(["Binance", "Bybit", "MEXC", "HTX"])

        self.add_pair_button = QPushButton("Add Pair")
        self.remove_pair_button = QPushButton("Remove Pair")
        self.edit_strategy_button = QPushButton("Edit Strategy")
        self.start_button = QPushButton("Start Selected")
        self.stop_button = QPushButton("Stop Selected")
        self.refresh_protection_button = QPushButton("Refresh Protection")
        self.cancel_protection_button = QPushButton("Cancel Protection")
        self.close_position_now_button = QPushButton("Close Position Now")
        self.cancel_all_orders_button = QPushButton("Cancel All Orders")

        button_layout.addWidget(QLabel("Exchange:"))
        button_layout.addWidget(self.exchange_selector)
        button_layout.addWidget(self.add_pair_button)
        button_layout.addWidget(self.remove_pair_button)
        button_layout.addWidget(self.edit_strategy_button)
        button_layout.addStretch()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.refresh_protection_button)
        button_layout.addWidget(self.cancel_protection_button)
        button_layout.addWidget(self.close_position_now_button)
        button_layout.addWidget(self.cancel_all_orders_button)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Pair", "Mode (Spot/Futures)", "Status", "Position", "DCA", "Avg Price", "Exchange"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.table, 1)

    def _connect_signals(self) -> None:
        self.add_pair_button.clicked.connect(self.add_pair)
        self.remove_pair_button.clicked.connect(self.remove_pair)
        self.edit_strategy_button.clicked.connect(self.edit_strategy)
        self.start_button.clicked.connect(self.start_pair)
        self.stop_button.clicked.connect(self.stop_pair)
        self.refresh_protection_button.clicked.connect(self.refresh_protection)
        self.cancel_protection_button.clicked.connect(self.cancel_protection)
        self.close_position_now_button.clicked.connect(self.close_position_now)
        self.cancel_all_orders_button.clicked.connect(self.cancel_all_orders)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.price_updated.connect(self._on_price_updated)
        self.edit_strategy_button.setEnabled(False)

    def _selected_row(self) -> int:
        return self.table.currentRow()

    def _selected_pair_name(self) -> str | None:
        row = self._selected_row()
        if row < 0:
            return None
        item = self.table.item(row, self.COL_PAIR)
        return item.text() if item else None

    def _selected_mode(self) -> str:
        row = self._selected_row()
        item = self.table.item(row, self.COL_MODE)
        return item.text() if item else "Spot"


    def _selected_status(self) -> str:
        row = self._selected_row()
        if row < 0:
            return "STOPPED"
        item = self.table.item(row, self.COL_STATUS)
        return item.text().upper() if item else "STOPPED"

    def _selected_exchange(self) -> str:
        row = self._selected_row()
        item = self.table.item(row, self.COL_EXCHANGE)
        return item.text() if item else "Binance"


    def _selected_pair_key(self) -> tuple[str, str, str] | None:
        pair_name = self._selected_pair_name()
        if not pair_name:
            return None
        exchange = self._selected_exchange()
        mode = self._selected_mode()
        return pair_name.upper(), exchange, mode

    def _find_pair_row(self, pair_name: str) -> int | None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_PAIR)
            if item and item.text().upper() == pair_name.upper():
                return row
        return None

    def _on_table_selection_changed(self) -> None:
        pair_name = self._selected_pair_name()
        self.edit_strategy_button.setEnabled(pair_name is not None)
        if pair_name is None:
            self.selected_pair_id = None
            return

        exchange = self._selected_exchange()
        mode = self._selected_mode()
        self.selected_pair_id = f"{pair_name.upper()}|{exchange}|{mode}"
        log(f"Selected pair: {pair_name.upper()} ({exchange}, {mode})")

    def emit_price_update(self, pair_name: str, price: float) -> None:
        self.price_updated.emit(pair_name, price)

    def _on_price_updated(self, pair_name: str, price: float) -> None:
        row = self._find_pair_row(pair_name)
        if row is None:
            return
        self.table.setItem(row, self.COL_PRICE, QTableWidgetItem(f"{price:.4f}"))
        self._refresh_row_state(pair_name)

    def _refresh_row_state(self, pair_name: str) -> None:
        row = self._find_pair_row(pair_name)
        if row is None:
            return

        worker = self.bot_manager.pairs.get(pair_name.upper())
        if worker is None:
            return

        task = self.bot_manager.tasks.get(pair_name.upper())
        status = "RUNNING" if task is not None and not task.done() else "STOPPED"
        position = worker.direction.upper() if worker.position_open else "NONE"
        dca_total = max(0, int(worker.strategy_settings.safety_orders_count))
        dca_used = max(0, int(worker.safety_orders_used))

        self.table.setItem(row, self.COL_STATUS, QTableWidgetItem(status))
        self.table.setItem(row, self.COL_POSITION, QTableWidgetItem(position))
        self.table.setItem(row, self.COL_DCA, QTableWidgetItem(f"{dca_used}/{dca_total}"))


    def load_pairs_from_manager(self) -> None:
        for pair_name, worker in self.bot_manager.pairs.items():
            if self._find_pair_row(pair_name) is not None:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, self.COL_PAIR, QTableWidgetItem(pair_name))
            self.table.setItem(row, self.COL_MODE, QTableWidgetItem(worker.mode))
            self.table.setItem(row, self.COL_STATUS, QTableWidgetItem("STOPPED"))
            self.table.setItem(row, self.COL_POSITION, QTableWidgetItem("NONE"))
            self.table.setItem(
                row,
                self.COL_DCA,
                QTableWidgetItem(f"{int(worker.safety_orders_used)}/{int(worker.strategy_settings.safety_orders_count)}"),
            )
            self.table.setItem(row, self.COL_PRICE, QTableWidgetItem("--"))
            self.table.setItem(row, self.COL_EXCHANGE, QTableWidgetItem(worker.exchange_name))
            self._refresh_row_state(pair_name)

    def _settings_for_mode(self, mode: str) -> StrategySettings:
        settings = self.get_settings()
        settings.mode = mode
        settings.enable_futures = mode.lower() == "futures"
        return settings


    def _is_valid_symbol(self, symbol: str) -> bool:
        symbol = symbol.strip().upper()
        return bool(re.fullmatch(r"[A-Z0-9]{5,20}", symbol))

    def add_pair(self) -> None:
        default_mode = "Futures" if self.get_settings().enable_futures else "Spot"
        dialog = AddPairDialog(default_mode, self.exchange_selector.currentText(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        pair_name, mode, exchange = dialog.get_values()
        if not self._is_valid_symbol(pair_name):
            QMessageBox.warning(self, "Invalid symbol", "Symbol must be 5..20 chars (A-Z, 0-9).")
            log("Invalid symbol for Add Pair")
            return

        if self._find_pair_row(pair_name) is not None:
            log(f"UI: {pair_name} already added")
            return

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, self.COL_PAIR, QTableWidgetItem(pair_name))
        self.table.setItem(row, self.COL_MODE, QTableWidgetItem(mode))
        self.table.setItem(row, self.COL_STATUS, QTableWidgetItem("STOPPED"))
        self.table.setItem(row, self.COL_POSITION, QTableWidgetItem("NONE"))
        self.table.setItem(row, self.COL_DCA, QTableWidgetItem(f"0/{int(self.get_settings().safety_orders_count)}"))
        self.table.setItem(row, self.COL_PRICE, QTableWidgetItem("--"))
        self.table.setItem(row, self.COL_EXCHANGE, QTableWidgetItem(exchange))

        settings = self._settings_for_mode(mode)
        self.bot_manager.update_pair_strategy_settings(pair_name, settings)
        self.bot_manager.add_pair(pair_name, mode, exchange)

    def edit_strategy(self) -> None:
        pair_name = self._selected_pair_name()
        row = self._selected_row()
        if not pair_name or row < 0:
            log("Select a pair first")
            return

        settings = self.bot_manager.get_pair_strategy_settings(pair_name)
        self._strategy_dialog = PairStrategyDialog(settings, self)
        log(f"Strategy opened for {pair_name.upper()}")
        if self._strategy_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        updated = self._strategy_dialog.get_settings()
        self.bot_manager.update_pair_strategy_settings(pair_name, updated)
        self.table.setItem(row, self.COL_MODE, QTableWidgetItem(updated.mode))
        self.table.setItem(row, self.COL_DCA, QTableWidgetItem(f"0/{int(updated.safety_orders_count)}"))
        self._refresh_row_state(pair_name)
        log(f"Strategy saved for {pair_name.upper()}")

    def remove_pair(self) -> None:
        row = self._selected_row()
        pair_name = self._selected_pair_name()
        if row < 0 or not pair_name:
            return

        self.loop.create_task(self.bot_manager.remove_pair(pair_name))
        self.table.removeRow(row)

    async def _run_start_pair(self, pair_name: str, mode: str, exchange: str) -> None:
        current = self.bot_manager.get_pair_strategy_settings(pair_name)
        current.mode = mode
        current.enable_futures = mode.lower() == "futures"
        self.bot_manager.update_pair_strategy_settings(pair_name, current)
        self.bot_manager.add_pair(pair_name, mode, exchange)
        await self.bot_manager.start_pair(pair_name)
        self._refresh_row_state(pair_name)
        log(f"Started: {pair_name.upper()} ({exchange}, {mode})")

    def start_pair(self) -> None:
        pair_key = self._selected_pair_key()
        row = self._selected_row()
        if pair_key is None or row < 0:
            log("Select a pair first")
            return

        pair_name, exchange, mode = pair_key

        if self._selected_status() == "RUNNING":
            log("Pair already running")
            return

        self.loop.create_task(self._run_start_pair(pair_name, mode, exchange))


    def _confirm_action(self, message: str) -> bool:
        reply = QMessageBox.question(
            self,
            "Confirm action",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    async def _run_refresh_protection(self, pair_name: str) -> None:
        await self.bot_manager.refresh_pair_protection(pair_name)
        log(f"Action completed: Refresh Protection for {pair_name}")

    async def _run_cancel_protection(self, pair_name: str) -> None:
        await self.bot_manager.cancel_pair_protection(pair_name)
        log(f"Action completed: Cancel Protection for {pair_name}")

    async def _run_close_position_now(self, pair_name: str) -> None:
        await self.bot_manager.close_pair_now(pair_name)
        self._refresh_row_state(pair_name)
        log(f"Action completed: Close Position Now for {pair_name}")

    async def _run_cancel_all_orders(self, pair_name: str) -> None:
        await self.bot_manager.cancel_pair_orders(pair_name)
        log(f"Action completed: Cancel All Orders for {pair_name}")

    def refresh_protection(self) -> None:
        pair_name = self._selected_pair_name()
        if not pair_name:
            log("Select a pair first")
            return
        self.loop.create_task(self._run_refresh_protection(pair_name))

    def cancel_protection(self) -> None:
        pair_name = self._selected_pair_name()
        if not pair_name:
            log("Select a pair first")
            return
        self.loop.create_task(self._run_cancel_protection(pair_name))

    def close_position_now(self) -> None:
        pair_name = self._selected_pair_name()
        if not pair_name:
            log("Select a pair first")
            return
        if not self._confirm_action("Are you sure? This will close position at market price."):
            return
        self.loop.create_task(self._run_close_position_now(pair_name))

    def cancel_all_orders(self) -> None:
        pair_name = self._selected_pair_name()
        if not pair_name:
            log("Select a pair first")
            return
        if not self._confirm_action("Are you sure? This will cancel all orders for selected pair."):
            return
        self.loop.create_task(self._run_cancel_all_orders(pair_name))

    def trigger_close_position_now(self) -> None:
        self.close_position_now()

    def trigger_refresh_protection(self) -> None:
        self.refresh_protection()

    def trigger_cancel_orders_for_pair(self) -> None:
        self.cancel_all_orders()

    async def _run_stop_pair(self, pair_name: str, mode: str, exchange: str) -> None:
        await self.bot_manager.stop_pair(pair_name)
        self._refresh_row_state(pair_name)
        log(f"Stopped: {pair_name.upper()} ({exchange}, {mode})")

    def stop_pair(self) -> None:
        pair_key = self._selected_pair_key()
        row = self._selected_row()
        if pair_key is None or row < 0:
            log("Select a pair first")
            return

        pair_name, exchange, mode = pair_key

        if self._selected_status() == "STOPPED":
            log("Pair already stopped")
            return

        self.loop.create_task(self._run_stop_pair(pair_name, mode, exchange))
