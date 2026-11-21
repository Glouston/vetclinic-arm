"""Диалог «Закрыть приём»: диагноз, жалобы, показатели, назначения; итог пересчитывается на лету."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                               QMessageBox, QPushButton, QSpinBox, QTableWidget, QWidget)

from app.models import PrescriptionInput
from app.repositories import catalog, stock
from app.services import visits
from app.ui.dialogs.base import BaseDialog
from app.util import fmt_money


class CloseVisitDialog(BaseDialog):
    def __init__(self, ctx, appointment, parent=None, allow_future: bool = False):
        super().__init__(ctx, f"Закрыть приём: {appointment.animal_name}, {appointment.service_name}", parent,
                         ok_text="Закрыть и начислить оплату")
        self.appt, self.allow_future = appointment, allow_future
        self.resize(760, 560)
        self.meds = ctx.query(catalog.list_medications, self) or []
        self.diagnosis = QLineEdit()
        self.complaints = QPlainTextEdit()
        self.complaints.setMaximumHeight(60)
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0, 500)
        self.weight.setDecimals(2)
        self.weight.setSpecialValueText("не измерялся")
        self.weight.setSuffix(" кг")
        self.temp = QDoubleSpinBox()
        self.temp.setRange(34.9, 43)
        self.temp.setDecimals(1)
        self.temp.setValue(34.9)
        self.temp.setSpecialValueText("не измерялась")
        self.temp.setSuffix(" °C")
        vit = QHBoxLayout()
        vit.addWidget(self.weight)
        vit.addWidget(self.temp)
        vit_w = QWidget()
        vit_w.setLayout(vit)
        self.form.addRow("Диагноз", self.diagnosis)
        self.form.addRow("Жалобы", self.complaints)
        self.form.addRow("Вес / температура", vit_w)

        # таблица назначений (форма ввода, строки — виджеты)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Препарат", "Дозировка", "Курс, дн.", "Кол-во", "На складе"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        add, rem = QPushButton("Добавить назначение"), QPushButton("Удалить назначение")
        add.clicked.connect(self.add_row)
        rem.clicked.connect(self.remove_row)
        btns = QHBoxLayout()
        btns.addWidget(add)
        btns.addWidget(rem)
        btns.addStretch()
        self.total = QLabel()
        self.total.setObjectName("priceLabel")
        self.body.insertWidget(1, QLabel("<b>Назначения</b> (препараты списываются со склада по FIFO):"))
        self.body.insertWidget(2, self.table)
        self.body.insertLayout(3, btns)
        self.body.insertWidget(4, self.total)
        self.recalc()

    def add_row(self) -> None:
        if not self.meds:
            QMessageBox.information(self, "Назначения", "Справочник препаратов пуст — сначала оформите приход на склад.")
            return
        r = self.table.rowCount()
        self.table.insertRow(r)
        med = QComboBox()
        for m in self.meds:
            med.addItem(f"{m.name}, {m.unit}", m.id)
        dosage = QLineEdit()
        dosage.setPlaceholderText("1 мл 2 раза в день")
        days, qty = QSpinBox(), QSpinBox()
        days.setRange(1, 365)
        days.setValue(5)
        qty.setRange(1, 10000)
        avail = QLabel()
        for col, w in enumerate([med, dosage, days, qty, avail]):
            self.table.setCellWidget(r, col, w)
        for w in (med, dosage):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.textChanged).connect(self.recalc)
        qty.valueChanged.connect(self.recalc)
        self.recalc()

    def remove_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self.recalc()

    def prescriptions(self) -> list[PrescriptionInput]:
        out = []
        for r in range(self.table.rowCount()):
            w = [self.table.cellWidget(r, c) for c in range(4)]
            out.append(PrescriptionInput(w[0].currentData(), w[1].text().strip(), w[2].value(), w[3].value()))
        return out

    def recalc(self) -> None:
        """Остатки по строкам + итог; недостаток подсвечивается красным (проверка дублируется транзакцией)."""
        need: dict[int, int] = {}
        for p in self.prescriptions():
            need[p.medication_id] = need.get(p.medication_id, 0) + p.qty
        ok = True
        for r, p in enumerate(self.prescriptions()):
            have = self.ctx.query(lambda c, m=p.medication_id: stock.available_qty(c, m, self.ctx.today()), self) or 0
            lbl: QLabel = self.table.cellWidget(r, 4)
            lbl.setText(str(have))
            short = need[p.medication_id] > have
            lbl.setStyleSheet("color: #c0392b; font-weight: bold;" if short else "")
            self.mark(self.table.cellWidget(r, 1), bool(p.dosage))
            ok &= bool(p.dosage)  # нехватка не блокирует: транзакция откатится с понятным сообщением
        left = self.appt.price_kopecks - self.appt.paid_kopecks
        prepaid = f" (внесено заранее {fmt_money(self.appt.paid_kopecks)})" if self.appt.paid_kopecks > 0 else ""
        self.total.setText(f"Стоимость приёма: {fmt_money(self.appt.price_kopecks)}{prepaid} · "
                           f"будет начислено к оплате: {fmt_money(max(left, 0))}")
        self.set_valid(ok, "Заполните дозировку у каждого назначения.")

    def on_accept(self) -> None:
        weight = self.weight.value() or None
        temp = self.temp.value() if self.temp.value() >= 35 else None
        ok, _ = self.ctx.execute(lambda c: visits.close_appointment(
            c, self.appt.id, self.diagnosis.text(), self.complaints.toPlainText(), self.prescriptions(),
            weight, temp, today=self.ctx.today(), allow_future=self.allow_future), self)
        if ok:
            self.accept()
