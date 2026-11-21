"""Раздел «Животные»: список с совместными фильтрами + карточка по двойному клику."""
from __future__ import annotations
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout)

from app.repositories import clients
from app.ui.dialogs.animal_card import AnimalCard
from app.ui.dialogs.simple import AnimalDialog
from app.ui.models.table_model import Col
from app.ui.pages.base import Page
from app.ui.widgets.common import VACC_COLOR, TableWithEmpty, col_date, col_status, page_header


class AnimalsPage(Page):
    title = "Животные"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск: кличка, владелец, телефон   (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.species = QComboBox()
        self.species.setMinimumWidth(130)
        self.sex = QComboBox()
        self.sex.addItem("Любой пол", None)
        self.sex.addItem("Самцы", "M")
        self.sex.addItem("Самки", "F")
        self.overdue = QCheckBox("только с просрочкой")
        reset = QPushButton("Сбросить")
        reset.setObjectName("link")
        add = QPushButton("＋  Животное")
        add.setObjectName("primary")
        reset.clicked.connect(self.reset_filters)
        add.clicked.connect(self.add_animal)
        self.table = TableWithEmpty([
            Col("Кличка", lambda a: a.name), Col("Вид", lambda a: a.species), Col("Порода", lambda a: a.breed),
            Col("Владелец", lambda a: a.owner_name), Col("Телефон", lambda a: a.owner_phone),
            col_date("Ближайшая ревакцинация", lambda a: a.next_due_date), col_status("Ревакцинация", lambda a: a.vacc_status)],
            row_color=lambda a: VACC_COLOR.get(a.vacc_status), hint="Нет животных по заданным фильтрам.")
        self.table.activated_row.connect(lambda a: self.open_card(a.id))
        self.count = QLabel()

        top = QHBoxLayout()
        for w in (self.search, self.species, self.sex, self.overdue, reset, add):
            top.addWidget(w, 3 if w is self.search else 0)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(page_header("Животные", "Найдите животное по кличке, владельцу или телефону. Двойной клик — карточка со всей историей."))
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        self.count.setObjectName("countLabel")
        legend = QLabel("Цвет строки: зелёный — ревакцинация в норме, жёлтый — скоро (≤ 30 дн.), красный — просрочена.")
        legend.setObjectName("legend")
        foot = QHBoxLayout()
        foot.addWidget(self.count)
        foot.addStretch()
        foot.addWidget(legend)
        lay.addLayout(foot)
        self._species_loaded = False
        for sig in (self.search.textChanged, self.sex.currentIndexChanged, self.overdue.toggled,
                    self.species.currentIndexChanged):
            sig.connect(lambda *_: self.refresh())

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def reset_filters(self) -> None:
        for w in (self.search, self.species, self.sex, self.overdue):
            w.blockSignals(True)
        self.search.clear()
        self.species.setCurrentIndex(0)
        self.sex.setCurrentIndex(0)
        self.overdue.setChecked(False)
        for w in (self.search, self.species, self.sex, self.overdue):
            w.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        super().refresh()
        s, sp, sx, od, today = (self.search.text(), self.species.currentData(), self.sex.currentData(),
                                self.overdue.isChecked(), self.ctx.today())
        self.load(lambda c: (clients.list_animals(c, s, sp, sx, od, today), clients.list_species(c)), self._fill)

    def _fill(self, data) -> None:
        rows, species = data
        if not self._species_loaded or self.species.count() != len(species) + 1:
            cur = self.species.currentData()
            self.species.blockSignals(True)
            self.species.clear()
            self.species.addItem("Любой вид", None)
            for sp in species:
                self.species.addItem(sp, sp)
            self.species.setCurrentIndex(max(0, self.species.findData(cur)))
            self.species.blockSignals(False)
            self._species_loaded = True
        self.table.set_rows(rows)
        self.count.setText(f"Найдено животных: {len(rows)}")

    def open_card(self, animal_id: int) -> None:
        AnimalCard(self.ctx, animal_id, self).exec()
        self.refresh()

    def add_animal(self) -> None:
        d = AnimalDialog(self.ctx, parent=self)
        if d.exec():
            QMessageBox.information(self, "Готово", "Животное добавлено.")
