"""Entry point for the trading bot desktop skeleton application."""

from __future__ import annotations

import asyncio
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core.bot_manager import BotManager
from ui.main_window import MainWindow


def _process_asyncio_events(loop: asyncio.AbstractEventLoop) -> None:
    """Process ready asyncio callbacks without blocking Qt UI thread."""
    loop.call_soon(loop.stop)
    loop.run_forever()


def main() -> int:
    """Create and run the Qt application with asyncio integration."""
    app = QApplication(sys.argv)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot_manager = BotManager(loop)
    window = MainWindow(bot_manager, loop)
    loop.run_until_complete(bot_manager.initialize())
    window.restore_pairs_from_manager()
    window.show()

    timer = QTimer()
    timer.timeout.connect(lambda: _process_asyncio_events(loop))
    timer.start(10)

    def _on_about_to_quit() -> None:
        timer.stop()
        loop.run_until_complete(bot_manager.shutdown())
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()

    app.aboutToQuit.connect(_on_about_to_quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
