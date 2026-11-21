"""Форматирование и разбор значений: деньги (копейки ↔ белорусские рубли), даты, телефон (Беларусь, +375)."""
from __future__ import annotations
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.errors import UserError

NBSP = " "
CURRENCY = "BYN"  # белорусский рубль
# коды операторов и городов Беларуси (две цифры после +375)
BY_CODES = {"25", "29", "33", "44", "15", "16", "17", "21", "22", "23"}


def today_iso() -> str:
    """Сегодняшняя дата; для демонстрации на тестовых данных можно задать VETCLINIC_TODAY=ГГГГ-ММ-ДД."""
    return os.environ.get("VETCLINIC_TODAY") or date.today().isoformat()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_money(kopecks: int | None) -> str:
    """150000 -> '1 500,00 BYN' (хранится в копейках, показывается в белорусских рублях)."""
    if kopecks is None:
        return ""
    sign = "-" if kopecks < 0 else ""
    rub, kop = divmod(abs(int(kopecks)), 100)
    return f"{sign}{rub:,}".replace(",", NBSP) + f",{kop:02d}{NBSP}{CURRENCY}"


def parse_money(text: str) -> int:
    """'1 250,5' -> 125050 копеек. Без float: через Decimal."""
    cleaned = (text or "").replace(NBSP, "").replace(" ", "").replace(CURRENCY, "").replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise UserError("Сумма введена неверно.") from None
    if value < 0:
        raise UserError("Сумма не может быть отрицательной.")
    return int((value * 100).to_integral_value())


def fmt_date(iso: str | None) -> str:
    """'2026-10-28' -> '28.10.2026'; datetime-строки тоже обрезаются до даты."""
    if not iso:
        return ""
    y, m, d = iso[:10].split("-")
    return f"{d}.{m}.{y}"


def fmt_datetime(iso: str | None) -> str:
    if not iso:
        return ""
    return fmt_date(iso) + (" " + iso[11:16] if len(iso) > 10 else "")


def normalize_phone(raw: str) -> str:
    """Белорусский номер в любом виде ('8 029 123-45-67', '+375 (29) 123-45-67') -> '+375291234567'."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("375"):
        digits = digits[3:]
    elif len(digits) == 11 and digits.startswith("80"):  # 8 0XX XXX-XX-XX — междугородний формат
        digits = digits[2:]
    elif len(digits) == 10 and digits.startswith("0"):   # 0XX XXX-XX-XX
        digits = digits[1:]
    if len(digits) != 9 or digits[:2] not in BY_CODES:
        raise UserError("Телефон должен быть белорусским: +375 XX XXX-XX-XX (код 25, 29, 33, 44 или городской).")
    return "+375" + digits


def is_valid_phone(raw: str) -> bool:
    try:
        normalize_phone(raw)
    except UserError:
        return False
    return True
