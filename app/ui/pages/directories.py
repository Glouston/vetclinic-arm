"""Справочники «Владельцы», «Врачи», «Услуги»: слева таблица, справа форма (Добавить/Сохранить/Удалить/Обновить)."""
from __future__ import annotations
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget)

from app.repositories import catalog, clients
from app.ui.dialogs.simple import PriceDialog
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.widgets.common import GREY, TableWithEmpty, col_date, col_money, col_status, page_header
from app.util import parse_money


class MasterDetailPage(Page):
    """Универсальный паттерн справочника. Наследник задаёт колонки, форму и операции."""
    heading = ""
    subtitle = "Выберите строку слева, чтобы изменить её, или нажмите «Добавить» для новой записи."
    hint = "Справочник пуст. Нажмите «Добавить»."
    columns: list[Col] = []
    row_color = None

    def __init__(self, ctx):
        super().__init__(ctx)
        self.current = None
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск   (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.table = TableWithEmpty(self.columns, self.row_color, self.hint)
        self.table.selection_changed.connect(self.on_select)
        self.form = QFormLayout()
        self.extra = QVBoxLayout()   # дополнительные блоки под формой (например, история цен)
        self.build_form(self.form)
        self.mode = QLabel()
        self.mode.setObjectName("pageHint")
        self.mode.setWordWrap(True)
        form_box = QGroupBox("Карточка")
        form_wrap = QVBoxLayout(form_box)
        form_wrap.addWidget(self.mode)
        form_wrap.addLayout(self.form)
        form_wrap.addLayout(self.extra)
        b_add, b_save = QPushButton("＋ Добавить"), QPushButton("Сохранить")
        b_add.setObjectName("link")
        b_del, b_ref = QPushButton("Удалить"), QPushButton("Обновить")
        b_save.setObjectName("primary")
        b_save.setMinimumWidth(120)
        b_del.setMinimumWidth(96)
        b_del.setObjectName("danger")
        b_ref.setObjectName("link")
        b_add.clicked.connect(self.new_item)
        b_save.clicked.connect(self.save_item)
        b_del.clicked.connect(self.delete_item)
        b_ref.clicked.connect(self.refresh)
        row = QHBoxLayout()   # основное действие — справа и крупно; вспомогательные — слева
        row.addWidget(b_add)
        row.addWidget(b_ref)
        row.addStretch()
        row.addWidget(b_del)
        row.addWidget(b_save)
        form_wrap.addLayout(row)
        form_wrap.addStretch()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.search)
        lv.addWidget(self.table, 1)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(form_box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setChildrenCollapsible(False)
        form_box.setMinimumWidth(480)
        form_box.setMaximumWidth(560)
        split.setSizes([680, 500])
        self._update_mode()
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header(self.heading, self.subtitle))
        lay.addWidget(split, 1)
        self.search.textChanged.connect(lambda *_: self.refresh())

    def focus_search(self) -> None:
        self.search.setFocus()

    # --- переопределяются ---
    def build_form(self, form: QFormLayout) -> None: ...
    def fetch(self, conn, search: str): ...
    def fill_form(self, item) -> None: ...
    def do_save(self, conn, item) -> None: ...
    def do_delete(self, conn, item) -> None: ...
    def describe(self, item) -> str: return ""

    def refresh(self) -> None:
        super().refresh()
        s = self.search.text()
        self.load(lambda c: self.fetch(c, s), self.table.set_rows)

    def on_select(self) -> None:
        self.current = self.table.selected()
        self.fill_form(self.current)
        self._update_mode()

    def new_item(self) -> None:
        self.table.view.clearSelection()
        self.current = None
        self.fill_form(None)
        self._update_mode()

    def _update_mode(self) -> None:
        self.mode.setText(f"Редактирование: {self.describe(self.current)}" if self.current
                          else "Новая запись — заполните поля и нажмите «Сохранить».")

    def save_item(self) -> None:
        item = self.current
        ok, _ = self.ctx.execute(lambda c: self.do_save(c, item), self)
        if ok:
            self.new_item()  # форма очищается: повторное «Сохранить» не создаст дубликат

    def delete_item(self) -> None:
        if self.current is None:
            QMessageBox.information(self, "Удаление", "Выберите запись в таблице.")
            return
        if QMessageBox.question(self, "Удаление", f"Удалить: {self.describe(self.current)}?") != QMessageBox.StandardButton.Yes:
            return
        item = self.current
        ok, _ = self.ctx.execute(lambda c: self.do_delete(c, item), self)  # RESTRICT -> понятное сообщение
        if ok:
            self.new_item()


class OwnersPage(MasterDetailPage):
    title = "Владельцы"
    heading = "Владельцы"
    columns = [Col("ФИО", lambda o: o.full_name), Col("Телефон", lambda o: o.phone),
               Col("Адрес", lambda o: o.address), Col("Email", lambda o: o.email),
               Col("Животных", lambda o: o.animals_count)]

    def build_form(self, form):
        self.name, self.phone, self.address, self.email = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.phone.setPlaceholderText("+375 29 123-45-67")
        for label, w in [("ФИО *", self.name), ("Телефон *", self.phone), ("Адрес", self.address), ("Email", self.email)]:
            form.addRow(label, w)

    def fetch(self, conn, search):
        return clients.list_owners(conn, search)

    def fill_form(self, o):
        self.name.setText(o.full_name if o else "")
        self.phone.setText(o.phone if o else "")
        self.address.setText(o.address or "" if o else "")
        self.email.setText(o.email or "" if o else "")

    def do_save(self, conn, o):
        args = (self.name.text(), self.phone.text(), self.address.text(), self.email.text())
        if o:
            clients.update_owner(conn, o.id, *args)
        else:
            clients.create_owner(conn, *args)

    def do_delete(self, conn, o):
        clients.delete_owner(conn, o.id)

    def describe(self, o):
        return o.full_name


class VetsPage(MasterDetailPage):
    title = "Врачи"
    heading = "Врачи"
    columns = [Col("ФИО", lambda v: v.full_name), Col("Специализация", lambda v: v.specialization),
               Col("Телефон", lambda v: v.phone), col_status("Работает", lambda v: "да" if v.is_active else "нет")]
    row_color = staticmethod(lambda v: None if v.is_active else GREY)

    def build_form(self, form):
        self.name, self.spec, self.phone = QLineEdit(), QComboBox(), QLineEdit()
        self.spec.setEditable(True)
        self.active = QCheckBox("Работает (доступен для записи)")
        self.active.setChecked(True)
        for label, w in [("ФИО *", self.name), ("Специализация *", self.spec), ("Телефон", self.phone), ("", self.active)]:
            form.addRow(label, w)

    def fetch(self, conn, search):
        return catalog.list_vets(conn, search=search)

    def refresh(self):
        super().refresh()
        self.ctx.run(catalog.list_specializations, self._set_specs, self)

    def _set_specs(self, specs):
        cur = self.spec.currentText()
        self.spec.clear()
        self.spec.addItems(specs)
        self.spec.setCurrentText(cur)

    def fill_form(self, v):
        self.name.setText(v.full_name if v else "")
        self.spec.setCurrentText(v.specialization if v else "")
        self.phone.setText(v.phone or "" if v else "")
        self.active.setChecked(bool(v.is_active) if v else True)

    def do_save(self, conn, v):
        catalog.save_vet(conn, v.id if v else None, self.name.text(), self.spec.currentText(), self.phone.text(),
                         self.active.isChecked())

    def do_delete(self, conn, v):
        catalog.delete_vet(conn, v.id)

    def describe(self, v):
        return v.full_name


class ServicesPage(MasterDetailPage):
    title = "Услуги"
    heading = "Услуги и прайс"
    columns = [Col("Услуга", lambda s: s.name), Col("Категория", lambda s: s.category),
               Col("Мин.", lambda s: s.duration_min), Col("Специализация", lambda s: s.required_specialization or "любая"),
               col_money("Цена сейчас", lambda s: s.price_kopecks)]

    def build_form(self, form):
        self.name, self.category = QLineEdit(), QComboBox()
        self.category.setEditable(True)
        self.duration = QSpinBox()
        self.duration.setRange(0, 600)
        self.duration.setSpecialValueText("не указано")
        self.spec = QComboBox()
        self.spec.setEditable(True)
        self.first_price = QLineEdit()
        self.first_price.setPlaceholderText("для новой услуги, BYN")
        for label, w in [("Название *", self.name), ("Категория", self.category), ("Длительность, мин", self.duration),
                         ("Нужна специализация", self.spec), ("Цена новой услуги", self.first_price)]:
            form.addRow(label, w)
        self.history = TableWithEmpty([col_money("Цена", lambda p: p.price_kopecks),
                                       col_date("С", lambda p: p.valid_from), col_date("По", lambda p: p.valid_to)],
                                      hint="Выберите услугу, чтобы увидеть историю цен.", sortable=False)
        self.history.setMaximumHeight(170)
        self.b_price = QPushButton("Новая версия цены…")
        self.b_price.clicked.connect(self.new_price)
        hist = QLabel("<b>История цен</b><br><span style='color:#6b7280'>Старая цена не правится — добавляется новая версия.</span>")
        hist.setWordWrap(True)
        self.extra.addWidget(hist)
        self.extra.addWidget(self.history)
        self.extra.addWidget(self.b_price)

    def fetch(self, conn, search):
        return catalog.list_services(conn, self.ctx.today(), search)

    def refresh(self):
        super().refresh()

        def meta(c):
            return catalog.list_categories(c), catalog.list_specializations(c)
        self.ctx.run(meta, self._set_meta, self)

    def _set_meta(self, data):
        cats, specs = data
        for combo, items, first in ((self.category, cats, ""), (self.spec, specs, "")):
            cur = combo.currentText()
            combo.clear()
            combo.addItems([first] + items)
            combo.setCurrentText(cur)

    def fill_form(self, s):
        self.name.setText(s.name if s else "")
        self.category.setCurrentText(s.category or "" if s else "")
        self.duration.setValue(s.duration_min or 0 if s else 0)
        self.spec.setCurrentText(s.required_specialization or "" if s else "")
        self.first_price.setEnabled(s is None)
        self.first_price.clear()
        self.b_price.setEnabled(s is not None)
        if s:
            self.ctx.run(lambda c: catalog.price_history(c, s.id), self.history.set_rows, self)
        else:
            self.history.set_rows([])

    def do_save(self, conn, s):
        price = parse_money(self.first_price.text()) if (s is None and self.first_price.text().strip()) else None
        catalog.save_service(conn, s.id if s else None, self.name.text(), self.category.currentText(),
                             self.duration.value() or None, self.spec.currentText(), price)

    def do_delete(self, conn, s):
        catalog.delete_service(conn, s.id)

    def describe(self, s):
        return s.name

    def new_price(self) -> None:
        if self.current and PriceDialog(self.ctx, self.current.id, self).exec():
            self.ctx.data_changed.emit()
            self.fill_form(self.current)
