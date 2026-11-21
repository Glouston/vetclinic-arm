"""Печать через QPrinter и открытие PDF-форм."""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile

from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QWidget


def print_html(parent: QWidget, html: str) -> None:
    """Диалог печати для HTML-содержимого."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle("Печать")
    if dialog.exec():
        doc = QTextDocument()
        doc.setHtml(f"<html><body style='font-family: Arial'>{html}</body></html>")
        doc.print_(printer)


def open_file(path: str) -> None:
    """Открывает файл в программе по умолчанию (PDF-просмотрщик)."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def temp_pdf_path(prefix: str) -> str:
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".pdf")
    os.close(fd)
    return path
