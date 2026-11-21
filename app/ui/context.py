"""Контекст приложения: путь к БД, фоновые запросы (QThreadPool), единая обработка ошибок.

В виджетах нет SQL: страницы вызывают ctx.run(...) / ctx.execute(...) с функциями репозиториев и сервисов.
"""
from __future__ import annotations
import logging
import sqlite3
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from app import db
from app.errors import UserError, to_user_message
from app.util import today_iso

log = logging.getLogger("vetclinic")


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, db_path, fn: Callable[[sqlite3.Connection], Any]):
        super().__init__()
        self.db_path, self.fn, self.signals = db_path, fn, _Signals()

    def run(self):
        try:
            conn = db.connect(self.db_path)  # своё соединение на поток
            try:
                result = self.fn(conn)
            finally:
                conn.close()
        except BaseException as exc:  # noqa: BLE001 — любая ошибка уходит в GUI-поток
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)


class AppContext(QObject):
    busy_changed = Signal(bool)   # для индикатора занятости в строке состояния
    data_changed = Signal()       # после записи в БД страницы обновляют списки

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.pool = QThreadPool.globalInstance()
        self._active = 0
        self._tasks: set[_Task] = set()

    @staticmethod
    def today() -> str:
        return today_iso()

    # ---- чтение: вне GUI-потока ------------------------------------------
    def run(self, fn: Callable, on_done: Callable[[Any], None], parent: QWidget | None = None) -> None:
        task = _Task(self.db_path, fn)
        self._tasks.add(task)
        task.setAutoDelete(False)
        self._set_active(+1)

        def finish():
            self._tasks.discard(task)
            self._set_active(-1)

        def ok(result):
            finish()
            on_done(result)

        def fail(exc):
            finish()
            self.show_error(exc, parent)

        task.signals.done.connect(ok)
        task.signals.failed.connect(fail)
        self.pool.start(task)

    def _set_active(self, delta: int) -> None:
        was = self._active > 0
        self._active += delta
        now = self._active > 0
        if was != now:
            if now:
                QApplication.setOverrideCursor(Qt_busy())
            else:
                QApplication.restoreOverrideCursor()
            self.busy_changed.emit(now)

    # ---- запись и короткие запросы: с обработкой ошибок ----------------------
    def execute(self, fn: Callable, parent: QWidget | None = None, notify: bool = True) -> tuple[bool, Any]:
        """Выполняет fn(conn) синхронно (короткая транзакция). Возвращает (успех, результат)."""
        try:
            conn = db.connect(self.db_path)
            try:
                result = fn(conn)
            finally:
                conn.close()
        except BaseException as exc:  # noqa: BLE001
            self.show_error(exc, parent)
            return False, None
        if notify:
            self.data_changed.emit()
        return True, result

    def query(self, fn: Callable, parent: QWidget | None = None) -> Any:
        """Короткое чтение для заполнения диалогов (справочники); ошибка -> None."""
        ok, result = self.execute(fn, parent, notify=False)
        return result if ok else None

    # ---- ошибки -----------------------------------------------------------
    def show_error(self, exc: BaseException, parent: QWidget | None = None) -> None:
        if not isinstance(exc, UserError):
            log.exception("Ошибка при работе с БД", exc_info=exc)  # подробности только в лог
        title = "Операция не выполнена" if isinstance(exc, (UserError, sqlite3.IntegrityError)) else "Ошибка"
        QMessageBox.critical(parent, title, to_user_message(exc))


def Qt_busy():
    from PySide6.QtCore import Qt
    return Qt.CursorShape.BusyCursor
