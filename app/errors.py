"""Ошибки приложения и перевод технических ошибок SQLite в понятные сообщения."""
from __future__ import annotations
import sqlite3


class UserError(Exception):
    """Ошибка, текст которой можно показать пользователю как есть."""


class InsufficientStock(UserError):
    """Недостаточно препарата на складе."""


class DatabaseUnavailable(UserError):
    """База данных недоступна."""


_UNIQUE = {
    "owners.phone": "Владелец с таким телефоном уже существует.",
    "appointments.vet_id": "Это время у врача уже занято.",
    "stock_batches.medication_id": "Партия с таким номером для этого препарата уже есть.",
    "service_prices.service_id": "Версия цены с такой датой начала уже существует.",
    "services.name": "Услуга с таким названием уже существует.",
    "medications.name": "Препарат с таким названием уже существует.",
    "visits.appointment_id": "Для этой записи приём уже оформлен.",
    "vaccinations.animal_id": "Такая вакцинация уже внесена.",
}


def to_user_message(exc: BaseException) -> str:
    """Понятное сообщение для пользователя; технические детали — только в лог."""
    if isinstance(exc, UserError):
        return str(exc)
    if isinstance(exc, sqlite3.IntegrityError):
        text = str(exc)
        if text.startswith("UNIQUE constraint failed"):
            for key, msg in _UNIQUE.items():
                if key in text:
                    return msg
            return "Такая запись уже существует."
        if text.startswith("FOREIGN KEY"):
            return "Операция невозможна: есть связанные записи или указана несуществующая запись."
        if text.startswith("NOT NULL"):
            return "Не заполнено обязательное поле."
        if text.startswith("CHECK"):
            return "Введено недопустимое значение."
        return text  # сообщение триггера (RAISE) уже на русском
    if isinstance(exc, sqlite3.OperationalError):
        return "База данных временно недоступна. Повторите попытку позже."
    return "Произошла непредвиденная ошибка. Подробности записаны в журнал."
