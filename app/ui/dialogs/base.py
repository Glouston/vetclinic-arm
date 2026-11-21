"""Базовый диалог: форма + OK/Отмена; OK активна только при валидной форме; Esc/Отмена ничего не сохраняют."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget

ERROR_STYLE = "border: 1px solid #c0392b; background: #fdecea;"


class BaseDialog(QDialog):
    def __init__(self, ctx, title: str, parent: QWidget | None = None, ok_text: str = "Сохранить"):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(title)
        self.setModal(True)
        self.form = QFormLayout()
        self.hint = QLabel()
        self.hint.setObjectName("errorHint")
        self.hint.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
        cancel = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("Отмена")
        cancel.setAutoDefault(False)
        cancel.setDefault(False)
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setDefault(True)   # акцентная кнопка — действие, а не «Отмена»
        ok.setObjectName("primary")
        self.buttons.accepted.connect(self.on_accept)
        self.buttons.rejected.connect(self.reject)  # данные не сохраняются
        self.form.setVerticalSpacing(10)
        self.form.setHorizontalSpacing(14)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 16)
        self.body.setSpacing(12)
        self.body.addLayout(self.form)
        self.body.addWidget(self.hint)
        self.body.addWidget(self.buttons)

    def mark(self, widget: QWidget, ok: bool) -> None:
        """Подсветка поля красным при ошибке."""
        widget.setStyleSheet("" if ok else ERROR_STYLE)

    def set_valid(self, ok: bool, message: str = "") -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        self.hint.setText("" if ok else message)

    def on_accept(self) -> None:  # переопределяется: выполнить действие и вызвать self.accept()
        self.accept()
