"""Exchanges setup tab UI."""

from __future__ import annotations

import asyncio

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.bot_manager import BotManager


class ExchangesTab(QWidget):
    """UI tab for exchange credentials and connection checks."""

    def __init__(self, bot_manager: BotManager, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.bot_manager = bot_manager
        self.loop = loop
        self.credentials: dict[str, dict[str, str]] = {
            "Binance": {"key": "", "secret": ""},
            "Bybit": {"key": "", "secret": ""},
            "MEXC": {"key": "", "secret": ""},
            "HTX": {"key": "", "secret": ""},
        }
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.exchange_dropdown = QComboBox()
        self.exchange_dropdown.addItems(["Binance", "Bybit", "MEXC", "HTX"])

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter API Key")

        self.secret_input = QLineEdit()
        self.secret_input.setPlaceholderText("Enter Secret")
        self.secret_input.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow("Exchange:", self.exchange_dropdown)
        form_layout.addRow("API Key:", self.api_key_input)
        form_layout.addRow("Secret:", self.secret_input)

        buttons_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.check_connection_button = QPushButton("Check Connection")
        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(self.check_connection_button)
        buttons_layout.addStretch()

        self.connection_status_label = QLabel("Connection status: not checked")

        main_layout.addLayout(form_layout)
        main_layout.addLayout(buttons_layout)
        main_layout.addWidget(self.connection_status_label)
        main_layout.addStretch()

    def _connect_signals(self) -> None:
        self.save_button.clicked.connect(self._save_credentials)
        self.check_connection_button.clicked.connect(self._check_connection)
        self.exchange_dropdown.currentTextChanged.connect(self._load_credentials)

    def _current_exchange(self) -> str:
        return self.exchange_dropdown.currentText()

    def _load_credentials(self) -> None:
        exchange = self._current_exchange()
        creds = self.credentials.get(exchange, {"key": "", "secret": ""})
        self.api_key_input.setText(creds.get("key", ""))
        self.secret_input.setText(creds.get("secret", ""))

    def _save_credentials(self) -> None:
        exchange = self._current_exchange()
        key = self.api_key_input.text().strip()
        secret = self.secret_input.text().strip()
        self.credentials[exchange] = {"key": key, "secret": secret}
        self.bot_manager.set_exchange_credentials(exchange, key, secret)
        self.connection_status_label.setText(f"{exchange} credentials saved")

    def _check_connection(self) -> None:
        exchange = self._current_exchange()

        async def _run() -> None:
            ok = await self.bot_manager.check_exchange_connection(exchange)
            status = "connected" if ok else "failed"
            self.connection_status_label.setText(f"{exchange} connection: {status}")

        self.loop.create_task(_run())
