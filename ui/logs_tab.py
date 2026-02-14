"""Logs tab UI."""

from __future__ import annotations

from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from utils.logger import register_listener, unregister_listener


class LogsTab(QWidget):
    """UI tab for application logs."""

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()
        register_listener(self.append_log)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setPlaceholderText("Application logs will appear here...")

        layout.addWidget(self.logs_text)

    def append_log(self, message: str) -> None:
        """Append new log line to text box."""
        self.logs_text.append(message)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        unregister_listener(self.append_log)
        super().closeEvent(event)
