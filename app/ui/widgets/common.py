"""Общие виджеты: таблица с пустым состоянием, плитка-счётчик, цвета статусов, форматтеры."""
from __future__ import annotations
from typing import Any, Callable

from PySide6.QtCore import QRectF, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QLabel, QStackedLayout, QStyle,
                               QStyledItemDelegate, QTableView, QVBoxLayout, QWidget)

from app.ui.models.table_model import BADGE_ROLE, Col, DataclassTableModel, make_proxy
from app.util import fmt_date, fmt_money

# светофор строк (мягкие тона) и «таблетки» статусов (насыщеннее)
GREEN, YELLOW, RED = QColor("#f1fbf4"), QColor("#fffbeb"), QColor("#fef3f2")
BLUE, GREY = QColor("#f3f8ff"), QColor("#f6f7f8")

_TONES = {  # фон, текст
    "green": ("#dcfce7", "#166534"), "yellow": ("#fef3c7", "#92400e"), "red": ("#fee2e2", "#991b1b"),
    "blue": ("#dbeafe", "#1e40af"), "grey": ("#f3f4f6", "#4b5563"),
}
STATUS_TONE = {
    "запланирован": "blue", "подтверждён": "green", "завершён": "grey", "отменён": "red",
    "просрочена": "red", "скоро": "yellow", "в норме": "green", "нет данных": "grey",
    "просрочен": "red", "истекает": "yellow",
    "оплачен": "green", "ожидает": "yellow", "возврат": "red",
    "запланировано": "blue", "выполнено": "green", "просрочено": "red",
    "да": "green", "нет": "grey",
}

APPT_STATUS_COLOR = {"запланирован": BLUE, "подтверждён": GREEN, "завершён": GREY, "отменён": RED}
VACC_COLOR = {"просрочена": RED, "скоро": YELLOW, "в норме": GREEN}
BATCH_COLOR = {"просрочен": RED, "истекает": YELLOW, "в норме": GREEN}
PAY_COLOR = {"оплачен": GREEN, "ожидает": YELLOW, "возврат": RED}
RIGHT = Qt.AlignmentFlag.AlignRight


def col_status(title: str, getter: Callable[[Any], Any]) -> Col:
    return Col(title, getter, badge=True)


class BadgeDelegate(QStyledItemDelegate):
    """Рисует значение статуса цветной «таблеткой»; остальные ячейки — стандартно."""

    def paint(self, painter: QPainter, option, index) -> None:
        text = index.data(BADGE_ROLE)
        if not text:
            return super().paint(painter, option, index)
        self.initStyleOption(option, index)
        option.text = ""
        style = option.widget.style() if option.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        bg, fg = _TONES[STATUS_TONE.get(str(text), "grey")]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(option.font)
        f.setPointSizeF(max(f.pointSizeF() - 1, 8))
        f.setWeight(QFont.Weight.DemiBold)
        painter.setFont(f)
        w = painter.fontMetrics().horizontalAdvance(str(text)) + 18
        h = painter.fontMetrics().height() + 6
        r = QRectF(option.rect.x() + 6, option.rect.center().y() - h / 2 + 1, w, h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(r, h / 2, h / 2)
        painter.setPen(QColor(fg))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, str(text))
        painter.restore()


def page_header(title: str, hint: str = "") -> QWidget:
    """Заголовок раздела + одна строка подсказки «что здесь можно сделать»."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("pageTitle")
    lay.addWidget(t)
    if hint:
        h = QLabel(hint)
        h.setObjectName("pageHint")
        h.setWordWrap(True)
        lay.addWidget(h)
    return w


def col_money(title: str, getter: Callable[[Any], Any]) -> Col:
    return Col(title, getter, fmt_money, RIGHT)


def col_date(title: str, getter: Callable[[Any], Any]) -> Col:
    return Col(title, getter, fmt_date)


class TableWithEmpty(QWidget):
    """QTableView + заглушка «Нет данных» с подсказкой, когда список пуст."""
    activated_row = Signal(object)   # двойной клик / Enter -> элемент dataclass
    selection_changed = Signal()

    def __init__(self, columns: list[Col], row_color=None, hint: str = "Измените фильтры или добавьте запись.",
                 sortable: bool = True):
        super().__init__()
        self.model = DataclassTableModel(columns, [], row_color)
        self.proxy: QSortFilterProxyModel = make_proxy(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(sortable)
        self.view.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)  # порядок из SQL, пока не кликнули
        self.view.setAlternatingRowColors(False)
        self.view.setShowGrid(False)
        self.view.setItemDelegate(BadgeDelegate(self.view))
        self.view.verticalHeader().setDefaultSectionSize(34)
        self.view.setMouseTracking(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.verticalHeader().setVisible(False)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.view.setWordWrap(False)
        self.view.doubleClicked.connect(lambda idx: self.activated_row.emit(self._item(idx)))
        self.view.selectionModel().selectionChanged.connect(lambda *_: self.selection_changed.emit())

        self.empty = QLabel(f"<p style='font-size:16px; color:#6b7280'><b>Нет данных</b></p><p>{hint}</p>")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName("emptyState")
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.empty)

    def _item(self, proxy_index):
        return self.model.row_at(self.proxy.mapToSource(proxy_index).row())

    def set_rows(self, rows: list) -> None:
        self.model.set_rows(rows)
        self.stack.setCurrentWidget(self.view if rows else self.empty)
        self.fit_columns()

    def fit_columns(self) -> None:
        """Ширина колонок по содержимому; если не помещается — пропорционально ужимаем (без гор. прокрутки)."""
        n = self.model.columnCount()
        for i in range(n):
            self.view.resizeColumnToContents(i)
        sb = self.view.verticalScrollBar()
        avail = self.view.width() - 2 * self.view.frameWidth() - (sb.sizeHint().width() if sb.isVisible() or
                                                                 self.model.rowCount() > 12 else 0) - 6
        widths = [self.view.columnWidth(i) for i in range(n)]
        total = sum(widths)
        if not n or avail < 300 or total <= avail:
            return
        # короткие колонки (дата, время, суммы, статус) не трогаем — ужимаем только длинные текстовые
        wide = [i for i, w in enumerate(widths) if w > 130]
        fixed = total - sum(widths[i] for i in wide)
        room = avail - fixed
        if wide and room > 0:
            k = room / sum(widths[i] for i in wide)
            for i in wide:
                self.view.setColumnWidth(i, max(110, int(widths[i] * k)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.model.rowCount():
            self.fit_columns()

    def selected(self):
        idx = self.view.currentIndex()
        return self._item(idx) if idx.isValid() and self.view.selectionModel().isSelected(idx) else None

    def row_count(self) -> int:
        return self.model.rowCount()


class StatTile(QFrame):
    """Плитка-счётчик дашборда; клик открывает соответствующий список."""
    clicked = Signal()

    def __init__(self, caption: str, accent: str = "#0f766e", link: str = "Открыть →"):
        super().__init__()
        self.setObjectName("tile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {accent}; border-radius: 5px;")
        self.value = QLabel("—")
        self.value.setObjectName("tileValue")
        cap = QLabel(caption)
        cap.setObjectName("tileCaption")
        cap.setWordWrap(True)
        more = QLabel(link)
        more.setObjectName("tileLink")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(4)
        lay.addWidget(dot)
        lay.addWidget(self.value)
        lay.addWidget(cap)
        lay.addStretch()
        lay.addWidget(more)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def set_value(self, n: int) -> None:
        self.value.setText(str(n))
