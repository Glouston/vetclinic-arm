"""Точка входа: python -m app.main"""
from __future__ import annotations
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app import db
from app.qt_env import ensure_qt_plugins_visible
from app.errors import UserError, to_user_message
from app.ui.context import AppContext
from app.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT.parent / "logs"


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "vetclinic.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        logging.getLogger("vetclinic").error("Необработанное исключение", exc_info=(exc_type, exc, tb))
        QMessageBox.critical(None, "Ошибка", to_user_message(exc))  # без технического трейса
    sys.excepthook = hook


def create_app(db_path=None) -> tuple[QApplication, MainWindow]:
    ensure_qt_plugins_visible()  # иначе на macOS Qt может не найти плагин платформы и аварийно завершиться
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("VetClinic")
    app.setApplicationName("ARM")
    qss = ROOT / "ui" / "theme.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    path = db_path or db.DEFAULT_DB
    db.init_db(path)  # разворачивает схему/данные только в пустой БД; существующие данные не трогает
    return app, MainWindow(AppContext(path))


def main() -> int:
    setup_logging()
    install_excepthook()
    try:
        app, window = create_app()
    except UserError as exc:
        ensure_qt_plugins_visible()
        QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "База данных недоступна", to_user_message(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
