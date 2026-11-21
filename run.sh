#!/bin/zsh
# Чистая установка и запуск: ./run.sh
# Пересоздаёт .venv на Python 3.13 (Homebrew), ставит зависимости, запускает приложение.
# Переменные: NO_RUN=1 — только установить; KEEP_VENV=1 — не пересоздавать .venv.
cd "$(dirname "$0")" || exit 1

# сбросить переменные, которые могли остаться в терминале от прежних попыток
unset QT_DEBUG_PLUGINS QT_QPA_PLATFORM QT_QPA_PLATFORM_PLUGIN_PATH QT_PLUGIN_PATH QT_LOGGING_RULES \
      DYLD_LIBRARY_PATH DYLD_FRAMEWORK_PATH VIRTUAL_ENV

PY=/opt/homebrew/bin/python3.13
[ -x "$PY" ] || { echo "Нет $PY. Установите: brew install python@3.13"; exit 1; }

if [ -z "$KEEP_VENV" ]; then
  rm -rf .venv .venv313
  "$PY" -m venv .venv || exit 1
fi
.venv/bin/python -m pip install -q -U pip || exit 1
.venv/bin/python -m pip install -q --no-compile -r requirements.txt || exit 1

# macOS может пометить файлы .venv в ~/Documents флагом hidden — Qt тогда не видит свои плагины
chflags -R nohidden .venv 2>/dev/null

echo "Проверка Qt…"
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
from PySide6.QtWidgets import QApplication
QApplication([]); print('Qt OK')" || exit 1

[ -n "$NO_RUN" ] && { echo "Установлено. Запуск: ./run.sh (с KEEP_VENV=1 — без переустановки)"; exit 0; }
VETCLINIC_TODAY=${VETCLINIC_TODAY:-2026-10-28} exec .venv/bin/python -m app.main
