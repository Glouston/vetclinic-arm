"""Базовый класс страницы раздела."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget


class Page(QWidget):
    title = ""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        ctx.data_changed.connect(self.on_data_changed)
        self._dirty = True
        self._token = 0

    def load(self, fn, on_done) -> None:
        """Фоновая загрузка; устаревшие ответы (пользователь уже поменял фильтр) отбрасываются."""
        self._token += 1
        token = self._token
        self.ctx.run(fn, lambda data: on_done(data) if token == self._token else None, self)

    def on_data_changed(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True  # обновим при следующем показе

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self._dirty = False

    def focus_search(self) -> None:
        pass

    def print_current(self) -> None:
        pass
