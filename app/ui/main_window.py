"""Главное окно: меню, панель инструментов, боковая навигация, QStackedWidget, строка состояния."""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QProgressBar, QSizePolicy, QStackedWidget, QStyle, QVBoxLayout, QWidget)

from app.services import reminders
from app.ui.dialogs.appointment import AppointmentDialog
from app.ui.icons import icon, nav_icon
from app.ui.dialogs.simple import ReceiptDialog
from app.ui.pages.animals import AnimalsPage
from app.ui.pages.appointments import AppointmentsPage
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.directories import OwnersPage, ServicesPage, VetsPage
from app.ui.pages.reminders import RemindersPage
from app.ui.pages.reports import ReportsPage
from app.ui.pages.stock import StockPage
from app.ui.pages.visits import VisitsPage
from app.util import fmt_date

S = QStyle.StandardPixmap


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("АРМ диспетчера ветеринарной клиники")
        self.resize(1280, 780)
        st = self.style()

        self.pages: dict[str, QWidget] = {}
        self.dashboard = DashboardPage(ctx)
        self.appointments = AppointmentsPage(ctx)
        self.reports = ReportsPage(ctx)
        sections = [("Главная", "home", self.dashboard),
                    ("Животные", "paw", AnimalsPage(ctx)),
                    ("Записи на приём", "calendar", self.appointments),
                    ("Приёмы", "check", VisitsPage(ctx)),
                    ("Склад", "box", StockPage(ctx)),
                    ("Владельцы", "users", OwnersPage(ctx)),
                    ("Врачи", "doctor", VetsPage(ctx)),
                    ("Услуги", "tag", ServicesPage(ctx)),
                    ("Отчёты", "chart", self.reports),
                    ("Напоминания", "bell", RemindersPage(ctx))]
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(QSize(18, 18))
        self.stack = QStackedWidget()
        for name, icon_name, page in sections:
            self.nav.addItem(QListWidgetItem(nav_icon(icon_name), name))
            page.setObjectName("page")
            page.setContentsMargins(14, 10, 14, 6)
            self.stack.addWidget(page)
            self.pages[name] = page
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)
        brand, brand_sub = QLabel("ВетКлиника"), QLabel("АРМ диспетчера")
        brand.setObjectName("brand")
        brand_sub.setObjectName("brandSub")
        sb_lay.addWidget(brand)
        sb_lay.addWidget(brand_sub)
        sb_lay.addWidget(self.nav, 1)
        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(sidebar)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.dashboard.new_appointment.connect(self.new_appointment)
        self.dashboard.close_visit.connect(lambda: self.goto("Записи на приём"))
        self.dashboard.open_reports.connect(lambda: self.goto("Отчёты"))
        self.dashboard.open_section.connect(self.open_from_dashboard)

        self._build_actions(st)
        self._build_status_bar()
        QShortcut(QKeySequence("Ctrl+F"), self, self.focus_search)
        QShortcut(QKeySequence("F5"), self, self.refresh_current)
        QShortcut(QKeySequence("Ctrl+P"), self, self.print_current)
        self.nav.setCurrentRow(0)
        self.restore_geometry()

    # ---- меню и панель инструментов ----------------------------------------------
    def _action(self, text, slot, shortcut=None, icon=None) -> QAction:
        a = QAction(icon or QIcon(), text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(lambda *_: slot())
        return a

    def _build_actions(self, st) -> None:
        a_new = self._action("Новая запись  Ctrl+N", self.new_appointment, "Ctrl+N", icon("plus"))
        a_close = self._action("Закрыть приём", lambda: self.goto("Записи на приём"), None, icon("close"))
        a_refresh = self._action("Обновить  F5", self.refresh_current, None, icon("refresh"))
        a_report = self._action("Отчёты", lambda: self.goto("Отчёты"), None, icon("chart"))
        a_exit = self._action("Выход", self.close, "Ctrl+Q")
        m = self.menuBar()
        m.addMenu("Файл").addActions([a_refresh, a_exit])
        ref = m.addMenu("Справочники")
        for name in ("Владельцы", "Врачи", "Услуги"):
            ref.addAction(self._action(name, lambda n=name: self.goto(n)))
        ops = m.addMenu("Операции")
        ops.addActions([a_new, a_close])
        ops.addAction(self._action("Приход на склад", self.receive_stock))
        ops.addAction(self._action("Сгенерировать напоминания", self.generate_reminders))
        rep = m.addMenu("Отчёты")
        for i, name in enumerate(("Оперативный", "Сводный", "Проблемный")):
            rep.addAction(self._action(name, lambda i=i: self.open_report(i)))
        help_ = m.addMenu("Справка")
        help_.addAction(self._action("Горячие клавиши", self.show_shortcuts))
        help_.addAction(self._action("О программе", self.show_about))
        tb = self.addToolBar("Основное")
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.addAction(a_new)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(a_refresh)

    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        sb.addPermanentWidget(QLabel("Пользователь: диспетчер"))
        sb.addPermanentWidget(QLabel(f"Рабочая дата: {fmt_date(self.ctx.today())}"))
        sb.addPermanentWidget(QLabel(f"● БД подключена ({Path(self.ctx.db_path).name})"))
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(120)
        self.busy.setTextVisible(False)
        self.busy.setVisible(False)
        sb.addPermanentWidget(self.busy)
        self.ctx.busy_changed.connect(self.busy.setVisible)
        sb.showMessage("Готово")

    # ---- действия ----------------------------------------------------------------
    def goto(self, name: str) -> None:
        self.nav.setCurrentRow(list(self.pages).index(name))

    def current_page(self):
        return self.stack.currentWidget()

    def new_appointment(self) -> None:
        AppointmentDialog(self.ctx, parent=self).exec()

    def receive_stock(self) -> None:
        if ReceiptDialog(self.ctx, self).exec():
            self.ctx.data_changed.emit()

    def generate_reminders(self) -> None:
        ok, n = self.ctx.execute(lambda c: reminders.generate(c, self.ctx.today()), self)
        if ok:
            QMessageBox.information(self, "Напоминания", f"Создано новых напоминаний: {n}.")

    def open_report(self, index: int) -> None:
        self.goto("Отчёты")
        self.reports.select_report(index)

    def open_from_dashboard(self, key: str) -> None:
        """Клик по плитке дашборда открывает раздел с уже применённым фильтром."""
        if key == "today":
            self.goto("Записи на приём")
            self.appointments.show_day(self.ctx.today())
        elif key == "unpaid":
            self.goto("Приёмы")
            self.pages["Приёмы"].only_debt.setChecked(True)
        elif key == "overdue":
            self.goto("Животные")
            self.pages["Животные"].overdue.setChecked(True)
        elif key == "expiring":
            self.goto("Склад")
            st = self.pages["Склад"]
            st.days.setValue(30)
            st.expiring.setChecked(True)

    def refresh_current(self) -> None:
        self.current_page().refresh()

    def focus_search(self) -> None:
        self.current_page().focus_search()

    def print_current(self) -> None:
        self.current_page().print_current()

    def show_shortcuts(self) -> None:
        QMessageBox.information(self, "Горячие клавиши",
                                "Ctrl+N — новая запись\nCtrl+F — поиск\nF5 — обновить\nCtrl+P — печать\nEsc — закрыть диалог")

    def show_about(self) -> None:
        QMessageBox.about(self, "О программе", "АРМ диспетчера ветеринарной клиники\n"
                                               "Курсовой проект по проектированию баз данных.\nPython · SQLite · PySide6")

    # ---- геометрия окна (QSettings) -------------------------------------------------
    def restore_geometry(self) -> None:
        s = QSettings("VetClinic", "ARM")
        geo = s.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        state = s.value("windowState")
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        s = QSettings("VetClinic", "ARM")
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        super().closeEvent(event)
