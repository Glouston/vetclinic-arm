"""Защита запуска Qt на macOS.

Если .venv лежит в синхронизируемой папке (например, ~/Documents), macOS может пометить его файлы
флагом «hidden». Qt при поиске плагинов пропускает скрытые файлы, не находит платформенный плагин
(libqcocoa.dylib) и аварийно завершает процесс («Python неожиданно завершил работу»).
Перед созданием QApplication снимаем этот флаг с плагинов Qt.
"""
from __future__ import annotations
import logging
import os
import stat
import sys
from pathlib import Path


def ensure_qt_plugins_visible() -> int:
    """Снимает UF_HIDDEN с плагинов PySide6. Возвращает число исправленных файлов (0 — вне macOS)."""
    if sys.platform != "darwin" or not hasattr(os, "chflags"):
        return 0
    try:
        import PySide6
    except ImportError:
        return 0
    plugins = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
    fixed = 0
    for path in [plugins, *plugins.rglob("*")]:
        try:
            flags = os.lstat(path).st_flags
            if flags & stat.UF_HIDDEN:
                os.chflags(path, flags & ~stat.UF_HIDDEN, follow_symlinks=False)
                fixed += 1
        except OSError:
            continue
    if fixed:
        logging.getLogger("vetclinic").warning("Сняты флаги hidden с %d файлов плагинов Qt", fixed)
    return fixed
