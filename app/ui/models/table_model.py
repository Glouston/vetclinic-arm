"""Универсальная QAbstractTableModel поверх списка dataclass + прокси для сортировки/фильтра."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
BADGE_ROLE = Qt.ItemDataRole.UserRole + 2   # текст статуса, который рисуется «таблеткой»


@dataclass
class Col:
    title: str
    value: Callable[[Any], Any]                       # «сырое» значение (по нему сортируем)
    fmt: Callable[[Any], str] | None = None           # отображение (рубли, дата ДД.ММ.ГГГГ …)
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft
    badge: bool = False                               # показывать значение цветной «таблеткой» статуса


class DataclassTableModel(QAbstractTableModel):
    def __init__(self, columns: list[Col], rows: list | None = None,
                 row_color: Callable[[Any], QColor | None] | None = None):
        super().__init__()
        self.columns, self._rows, self.row_color = columns, list(rows or []), row_color

    def set_rows(self, rows: list) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, row: int):
        return self._rows[row]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section].title
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item, col = self._rows[index.row()], self.columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            v = col.value(item)
            return col.fmt(v) if col.fmt else ("" if v is None else str(v))
        if role == BADGE_ROLE:
            return col.value(item) if col.badge else None
        if role == SORT_ROLE:
            v = col.value(item)
            return "" if v is None else v
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(col.align | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole and self.row_color:
            return self.row_color(item)
        return None


def make_proxy(model: DataclassTableModel) -> QSortFilterProxyModel:
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setSortRole(SORT_ROLE)
    proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    return proxy
