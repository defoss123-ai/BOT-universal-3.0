"""Strategy settings tab UI."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from strategy.base_strategy import StrategySettings


class StrategyTab(QWidget):
    """UI tab for strategy parameters."""

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.take_profit_input = QLineEdit("1.0")
        self.safety_step_input = QLineEdit("2.0")
        self.base_order_size_input = QLineEdit("25")
        self.safety_orders_count_input = QLineEdit("3")
        self.volume_multiplier_input = QLineEdit("1.5")
        self.commission_input = QLineEdit("0.1")
        self.order_timeout_input = QLineEdit("30")

        self.rsi_period_input = QLineEdit("14")
        self.rsi_level_input = QLineEdit("30")
        self.ema_period_input = QLineEdit("200")
        self.adx_period_input = QLineEdit("14")
        self.adx_threshold_input = QLineEdit("20")
        self.volume_spike_multiplier_input = QLineEdit("1.5")
        self.atr_min_value_input = QLineEdit("0")
        self.risk_per_trade_input = QLineEdit("1.0")
        self.max_total_exposure_input = QLineEdit("30.0")

        self.position_size_mode_dropdown = QComboBox()
        self.position_size_mode_dropdown.addItems(["Fixed", "Risk-based"])

        self.timeframe_dropdown = QComboBox()
        self.timeframe_dropdown.addItems(["1m", "5m", "15m", "1h"])

        self.run_mode_dropdown = QComboBox()
        self.run_mode_dropdown.addItems(["Live", "Paper", "Backtest"])

        self.use_market_first_order_checkbox = QCheckBox("Use Market First Order")
        self.use_market_first_order_checkbox.setChecked(True)

        self.enable_futures_checkbox = QCheckBox("Enable Futures")
        self.enable_futures_checkbox.setChecked(False)

        self.protection_orders_checkbox = QCheckBox("Protection Orders on Exchange")
        self.protection_orders_checkbox.setChecked(True)

        self.auto_resume_checkbox = QCheckBox("Auto Resume Running Pairs")
        self.auto_resume_checkbox.setChecked(False)

        self.stop_loss_mode_dropdown = QComboBox()
        self.stop_loss_mode_dropdown.addItems(["Off", "Always", "After Last Safety"])
        self.use_rsi_checkbox = QCheckBox("Use RSI")
        self.use_rsi_checkbox.setChecked(True)
        self.use_ema_filter_checkbox = QCheckBox("Use EMA Trend Filter")
        self.use_ema_filter_checkbox.setChecked(True)
        self.use_adx_filter_checkbox = QCheckBox("Use ADX Filter")
        self.use_adx_filter_checkbox.setChecked(True)
        self.use_volume_filter_checkbox = QCheckBox("Use Volume Filter")
        self.use_atr_filter_checkbox = QCheckBox("Use ATR Filter")

        self.leverage_input = QLineEdit("5")

        self.margin_dropdown = QComboBox()
        self.margin_dropdown.addItems(["Cross", "Isolated"])

        self.break_even_after_input = QLineEdit("0.3")
        self.stop_loss_pct_input = QLineEdit("1.0")
        self.cooldown_minutes_input = QLineEdit("0")

        self.direction_dropdown = QComboBox()
        self.direction_dropdown.addItems(["Long", "Short"])

        form.addRow("Take Profit %:", self.take_profit_input)
        form.addRow("Safety Step %:", self.safety_step_input)
        form.addRow("Base Order Size (USDT):", self.base_order_size_input)
        form.addRow("Safety Orders Count:", self.safety_orders_count_input)
        form.addRow("Volume Multiplier:", self.volume_multiplier_input)
        form.addRow("Commission %:", self.commission_input)
        form.addRow("Order Timeout (sec):", self.order_timeout_input)

        form.addRow("RSI Period:", self.rsi_period_input)
        form.addRow("RSI Level:", self.rsi_level_input)
        form.addRow("EMA Period:", self.ema_period_input)
        form.addRow("ADX Period:", self.adx_period_input)
        form.addRow("ADX Threshold:", self.adx_threshold_input)
        form.addRow("Volume Spike Multiplier:", self.volume_spike_multiplier_input)
        form.addRow("ATR Min Value:", self.atr_min_value_input)
        form.addRow("Position size mode:", self.position_size_mode_dropdown)
        form.addRow("Risk per trade (%):", self.risk_per_trade_input)
        form.addRow("Max total exposure (%):", self.max_total_exposure_input)
        form.addRow("Timeframe:", self.timeframe_dropdown)
        form.addRow("Run mode:", self.run_mode_dropdown)

        form.addRow("Leverage:", self.leverage_input)
        form.addRow("Margin Mode:", self.margin_dropdown)
        form.addRow("Break-even after (%):", self.break_even_after_input)
        form.addRow("Stop Loss Mode:", self.stop_loss_mode_dropdown)
        form.addRow("Stop Loss (%):", self.stop_loss_pct_input)
        form.addRow("Cooldown minutes:", self.cooldown_minutes_input)
        form.addRow("Futures Position Side:", self.direction_dropdown)

        layout.addLayout(form)
        layout.addWidget(self.use_market_first_order_checkbox)
        layout.addWidget(self.enable_futures_checkbox)
        layout.addWidget(self.protection_orders_checkbox)
        layout.addWidget(self.auto_resume_checkbox)
        layout.addWidget(self.use_rsi_checkbox)
        layout.addWidget(self.use_ema_filter_checkbox)
        layout.addWidget(self.use_adx_filter_checkbox)
        layout.addWidget(self.use_volume_filter_checkbox)
        layout.addWidget(self.use_atr_filter_checkbox)
        layout.addStretch()

    def get_strategy_settings(self) -> StrategySettings:
        """Read strategy settings from UI with safe defaults."""

        def as_int(value: str, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def as_float(value: str, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        return StrategySettings(
            rsi_period=as_int(self.rsi_period_input.text(), 14),
            rsi_level=as_float(self.rsi_level_input.text(), 30.0),
            ema_period=as_int(self.ema_period_input.text(), 200),
            adx_period=as_int(self.adx_period_input.text(), 14),
            timeframe=self.timeframe_dropdown.currentText(),
            take_profit_pct=as_float(self.take_profit_input.text(), 1.0),
            base_order_size_usdt=as_float(self.base_order_size_input.text(), 25.0),
            order_timeout_sec=as_int(self.order_timeout_input.text(), 30),
            use_market_order=self.use_market_first_order_checkbox.isChecked(),
            safety_step_pct=as_float(self.safety_step_input.text(), 2.0),
            safety_orders_count=as_int(self.safety_orders_count_input.text(), 3),
            volume_multiplier=as_float(self.volume_multiplier_input.text(), 1.5),
            commission_pct=as_float(self.commission_input.text(), 0.1),
            enable_futures=self.enable_futures_checkbox.isChecked(),
            leverage=as_int(self.leverage_input.text(), 5),
            margin_mode=self.margin_dropdown.currentText(),
            break_even_after_percent=as_float(self.break_even_after_input.text(), 0.3),
            futures_position_side=self.direction_dropdown.currentText(),
            mode="Futures" if self.enable_futures_checkbox.isChecked() else "Spot",
            cooldown_minutes=as_float(self.cooldown_minutes_input.text(), 0.0),
            run_mode=self.run_mode_dropdown.currentText(),
            use_rsi=self.use_rsi_checkbox.isChecked(),
            use_ema_trend_filter=self.use_ema_filter_checkbox.isChecked(),
            use_adx_filter=self.use_adx_filter_checkbox.isChecked(),
            use_volume_filter=self.use_volume_filter_checkbox.isChecked(),
            use_atr_filter=self.use_atr_filter_checkbox.isChecked(),
            adx_threshold=as_float(self.adx_threshold_input.text(), 20.0),
            volume_spike_multiplier=as_float(self.volume_spike_multiplier_input.text(), 1.5),
            atr_min_value=as_float(self.atr_min_value_input.text(), 0.0),
            position_size_mode=self.position_size_mode_dropdown.currentText(),
            risk_per_trade_pct=as_float(self.risk_per_trade_input.text(), 1.0),
            max_total_exposure_pct=as_float(self.max_total_exposure_input.text(), 30.0),
            protection_orders_on_exchange=self.protection_orders_checkbox.isChecked(),
            stop_loss_mode=self.stop_loss_mode_dropdown.currentText(),
            enable_stop_loss=self.stop_loss_mode_dropdown.currentText() != "Off",
            stop_loss_pct=as_float(self.stop_loss_pct_input.text(), 1.0),
            auto_resume_running_pairs=self.auto_resume_checkbox.isChecked(),
        )
