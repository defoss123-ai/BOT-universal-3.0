"""Statistics and backtesting tab UI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.bot_manager import BotManager
from strategy.base_strategy import StrategySettings
from utils.logger import log


class StatisticsTab(QWidget):
    """UI tab for trade statistics and backtest report."""

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
        self._figure_canvas: Any | None = None
        self._figure_ax: Any | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.symbol_combo = QComboBox()
        self.symbol_combo.setEditable(True)
        self._refresh_pairs()

        self.timeframe_label = QLabel("Uses Strategy Tab timeframe")
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())

        form.addRow("Backtest pair:", self.symbol_combo)
        form.addRow("Timeframe:", self.timeframe_label)
        form.addRow("Start date:", self.start_date)
        form.addRow("End date:", self.end_date)

        button_row = QHBoxLayout()
        self.refresh_pairs_button = QPushButton("Refresh pairs")
        self.refresh_pairs_button.clicked.connect(self._refresh_pairs)
        self.run_backtest_button = QPushButton("Run Backtest")
        self.run_backtest_button.clicked.connect(self._run_backtest)
        button_row.addWidget(self.refresh_pairs_button)
        button_row.addWidget(self.run_backtest_button)
        button_row.addStretch()

        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])

        self.graph_placeholder_label = QLabel("Equity Curve")

        layout.addLayout(form)
        layout.addLayout(button_row)
        layout.addWidget(self.stats_table)
        layout.addWidget(self.graph_placeholder_label)
        self._init_plot_widget(layout)

    def _refresh_pairs(self) -> None:
        current = self.symbol_combo.currentText()
        self.symbol_combo.clear()
        pairs = list(self.bot_manager.pairs.keys())
        if not pairs:
            pairs = ["BTCUSDT"]
        self.symbol_combo.addItems(pairs)
        if current:
            self.symbol_combo.setCurrentText(current)

    def _init_plot_widget(self, layout: QVBoxLayout) -> None:
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except Exception:  # noqa: BLE001
            self.graph_placeholder_label.setText("Equity Curve (install matplotlib for chart)")
            return

        figure = Figure(figsize=(6, 2.5))
        self._figure_ax = figure.add_subplot(111)
        self._figure_canvas = FigureCanvasQTAgg(figure)
        layout.addWidget(self._figure_canvas)

    def _run_backtest(self) -> None:
        self.run_backtest_button.setEnabled(False)
        self.loop.create_task(self._run_backtest_async())

    async def _run_backtest_async(self) -> None:
        try:
            settings: StrategySettings = self.get_settings()
            settings.run_mode = "Backtest"
            pair = self.symbol_combo.currentText().upper().strip() or "BTCUSDT"
            start_date = self.start_date.date().toString("yyyy-MM-dd")
            end_date = self.end_date.date().toString("yyyy-MM-dd")
            report, equity = await self.bot_manager.run_backtest(
                pair=pair,
                timeframe=settings.timeframe,
                start_date=start_date,
                end_date=end_date,
                settings=settings,
            )
            self._fill_report(report)
            self._draw_equity(equity)
        except Exception as exc:  # noqa: BLE001
            log(f"Backtest failed: {exc}")
        finally:
            self.run_backtest_button.setEnabled(True)

    def _fill_report(self, report: dict[str, float | int]) -> None:
        self.stats_table.setRowCount(0)
        for metric, value in report.items():
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            self.stats_table.setItem(row, 0, QTableWidgetItem(metric))
            if isinstance(value, float):
                formatted = f"{value:.6f}"
            else:
                formatted = str(value)
            self.stats_table.setItem(row, 1, QTableWidgetItem(formatted))

    def _draw_equity(self, equity: list[float]) -> None:
        if self._figure_canvas is None or self._figure_ax is None:
            self.graph_placeholder_label.setText(f"Equity points: {len(equity)}")
            return
        self._figure_ax.clear()
        self._figure_ax.plot(equity)
        self._figure_ax.set_title("Equity Curve")
        self._figure_ax.grid(True, alpha=0.3)
        self._figure_canvas.draw_idle()
