"""Optimizer tab for strategy grid search."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.bot_manager import BotManager
from strategy.base_strategy import StrategySettings
from utils.logger import log


class OptimizerTab(QWidget):
    """UI tab for asynchronous grid-search optimization."""

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
        self._last_results: list[dict] = []
        self._last_top_results: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.pair_combo = QComboBox()
        self.pair_combo.setEditable(True)
        self.apply_pair_combo = QComboBox()
        self.apply_pair_combo.setEditable(True)
        self._refresh_pairs()

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-2))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())

        self.rsi_period_range = QLineEdit("10,20,1")
        self.rsi_level_range = QLineEdit("20,35,5")
        self.take_profit_range = QLineEdit("0.5,2.0,0.5")
        self.safety_step_range = QLineEdit("0.5,3.0,0.5")
        self.volume_multiplier_range = QLineEdit("1.2,2.0,0.2")
        self.safety_count_range = QLineEdit("1,5,1")
        self.break_even_range = QLineEdit("0.2,1.0,0.2")

        form.addRow("Optimize symbol", self.pair_combo)
        form.addRow("Apply target pair", self.apply_pair_combo)
        form.addRow("Start date", self.start_date)
        form.addRow("End date", self.end_date)
        form.addRow("RSI period range", self.rsi_period_range)
        form.addRow("RSI level range", self.rsi_level_range)
        form.addRow("Take Profit % range", self.take_profit_range)
        form.addRow("Safety Step % range", self.safety_step_range)
        form.addRow("Volume Multiplier range", self.volume_multiplier_range)
        form.addRow("Safety Orders Count range", self.safety_count_range)
        form.addRow("Break-even % range", self.break_even_range)

        button_row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh pairs")
        self.refresh_button.clicked.connect(self._refresh_pairs)
        self.run_button = QPushButton("Run Optimization")
        self.run_button.clicked.connect(self._run_optimization)
        self.apply_button = QPushButton("Apply to Pair")
        self.apply_button.clicked.connect(self._apply_to_pair)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.apply_button)
        button_row.addStretch()

        self.status_label = QLabel("Ready")

        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(
            ["Rank", "Profit Factor", "Max DD", "Total Profit", "Win Rate", "Params"]
        )

        layout.addLayout(form)
        layout.addLayout(button_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results_table)

    def _refresh_pairs(self) -> None:
        current_opt = self.pair_combo.currentText()
        current_apply = self.apply_pair_combo.currentText()
        pairs = list(self.bot_manager.pairs.keys())
        if not pairs:
            pairs = ["BTCUSDT"]

        self.pair_combo.clear()
        self.pair_combo.addItems(pairs)
        if current_opt:
            self.pair_combo.setCurrentText(current_opt)

        self.apply_pair_combo.clear()
        self.apply_pair_combo.addItems(pairs)
        if current_apply:
            self.apply_pair_combo.setCurrentText(current_apply)

    def _parse_range(self, value: str, *, cast: type[float] | type[int]) -> list[float | int]:
        parts = [x.strip() for x in value.split(",")]
        if len(parts) != 3:
            raise ValueError(f"Invalid range format: {value}")
        start = float(parts[0])
        end = float(parts[1])
        step = float(parts[2])
        if step <= 0:
            raise ValueError("Range step must be > 0")

        values: list[float | int] = []
        current = start
        while current <= end + 1e-9:
            values.append(int(round(current)) if cast is int else round(current, 6))
            current += step
        return values

    def _build_parameter_ranges(self) -> dict[str, list[float | int]]:
        return {
            "rsi_period": self._parse_range(self.rsi_period_range.text(), cast=int),
            "rsi_level": self._parse_range(self.rsi_level_range.text(), cast=float),
            "take_profit_pct": self._parse_range(self.take_profit_range.text(), cast=float),
            "safety_step_pct": self._parse_range(self.safety_step_range.text(), cast=float),
            "volume_multiplier": self._parse_range(self.volume_multiplier_range.text(), cast=float),
            "safety_orders_count": self._parse_range(self.safety_count_range.text(), cast=int),
            "break_even_after_percent": self._parse_range(self.break_even_range.text(), cast=float),
        }

    def _run_optimization(self) -> None:
        self.run_button.setEnabled(False)
        self.loop.create_task(self._run_optimization_async())

    async def _run_optimization_async(self) -> None:
        try:
            settings = self.get_settings()
            settings.run_mode = "Backtest"
            symbol = self.pair_combo.currentText().upper().strip() or "BTCUSDT"
            start_date = self.start_date.date().toString("yyyy-MM-dd")
            end_date = self.end_date.date().toString("yyyy-MM-dd")
            parameter_ranges = self._build_parameter_ranges()

            self.status_label.setText("Optimization in progress...")
            results = await self.bot_manager.run_optimization(
                pair=symbol,
                timeframe=settings.timeframe,
                start_date=start_date,
                end_date=end_date,
                parameter_ranges=parameter_ranges,
                base_settings=settings,
            )
            self._last_results = results
            self._last_top_results = results[:10]
            self._fill_results(self._last_top_results)
            self.status_label.setText(f"Completed. Tested: {len(results)} combinations")
            log(f"Optimization complete for {symbol}. Top 10 ready")
        except Exception as exc:  # noqa: BLE001
            self.status_label.setText(f"Failed: {exc}")
            log(f"Optimizer failed: {exc}")
        finally:
            self.run_button.setEnabled(True)

    def _fill_results(self, top_results: list[dict]) -> None:
        self.results_table.setRowCount(0)
        for rank, row in enumerate(top_results, start=1):
            table_row = self.results_table.rowCount()
            self.results_table.insertRow(table_row)
            self.results_table.setItem(table_row, 0, QTableWidgetItem(str(rank)))
            self.results_table.setItem(table_row, 1, QTableWidgetItem(f"{float(row['profit_factor']):.6f}"))
            self.results_table.setItem(table_row, 2, QTableWidgetItem(f"{float(row['max_drawdown']):.6f}"))
            self.results_table.setItem(table_row, 3, QTableWidgetItem(f"{float(row['total_profit']):.6f}"))
            self.results_table.setItem(table_row, 4, QTableWidgetItem(f"{float(row['win_rate']):.2f}"))
            self.results_table.setItem(table_row, 5, QTableWidgetItem(str(row["params"])))

    def _apply_to_pair(self) -> None:
        selected_row = self.results_table.currentRow()
        if selected_row < 0 or selected_row >= len(self._last_top_results):
            return

        result = self._last_top_results[selected_row]
        params = result.get("params", {})
        pair = self.apply_pair_combo.currentText().upper().strip()
        if not pair:
            return

        settings = self.bot_manager.get_pair_strategy_settings(pair)
        for key, value in params.items():
            setattr(settings, key, value)
        settings.run_mode = "Live"
        self.bot_manager.update_pair_strategy_settings(pair, settings)
        self.status_label.setText(f"Applied strategy to {pair}")
        log(f"Optimizer parameters applied to {pair}")
