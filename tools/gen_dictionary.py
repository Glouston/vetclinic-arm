"""Генерирует docs/словарь_данных.md из фактической схемы БД (PRAGMA) — всегда соответствует schema.sql.

Запуск: python tools/gen_dictionary.py
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TABLES = {
    "owners": "Владельцы животных (клиенты клиники)", "animals": "Животные-пациенты",
    "vets": "Врачи со специализациями", "services": "Справочник услуг",
    "service_prices": "История цен услуг (версии с периодом действия)",
    "appointments": "Записи на приём (цена фиксируется на момент записи)",
    "visits": "Фактические приёмы (создаются при закрытии записи)",
    "medications": "Справочник препаратов и вакцин", "prescriptions": "Назначения препаратов по приёму",
    "stock_batches": "Партии препаратов на складе", "stock_movements": "Журнал движений склада",
    "payments": "Платежи по записям на приём (предоплата или оплата после приёма)", "vaccinations": "Вакцинации животных", "vital_signs": "Измерения веса и температуры",
    "reminders": "Напоминания (ревакцинация, повторный приём, оплата)",
}
FIELDS = {
    "id": "Суррогатный первичный ключ", "owner_id": "Владелец", "animal_id": "Животное", "vet_id": "Врач",
    "service_id": "Услуга", "visit_id": "Приём", "appointment_id": "Запись на приём", "medication_id": "Препарат",
    "batch_id": "Партия склада", "full_name": "ФИО", "phone": "Телефон в формате +375XXXXXXXXX (уникален)",
    "address": "Адрес", "email": "Электронная почта", "name": "Название / кличка", "species": "Вид животного",
    "breed": "Порода", "birth_date": "Дата рождения (ISO)", "sex": "Пол: M — самец, F — самка", "notes": "Заметки",
    "specialization": "Специализация врача", "is_active": "Работает: 1 — да, 0 — нет", "category": "Категория услуги",
    "duration_min": "Длительность, минут", "required_specialization": "Требуемая специализация врача (NULL — любая)",
    "price_kopecks": "Цена в копейках (целое, без FLOAT)", "valid_from": "Начало действия цены", "valid_to": "Конец действия (NULL — текущая)",
    "appt_date": "Дата приёма (ISO)", "appt_time": "Время приёма ЧЧ:ММ", "status": "Статус (набор ограничен CHECK)",
    "created_at": "Момент создания записи", "diagnosis": "Диагноз (NULL — ещё не установлен)", "complaints": "Жалобы",
    "closed_at": "Момент закрытия приёма", "unit": "Единица измерения", "dosage": "Дозировка", "course_days": "Длительность курса, дней",
    "qty": "Количество (единицы препарата)", "batch_no": "Серия партии", "expiry_date": "Срок годности (ISO)",
    "qty_delta": "Изменение остатка (+приход, −списание)", "reason": "Причина движения", "moved_at": "Момент движения",
    "amount_kopecks": "Сумма в копейках", "method": "Способ оплаты", "paid_at": "Момент оплаты", "vacc_date": "Дата вакцинации",
    "next_due_date": "Срок ревакцинации", "weight_kg": "Вес, кг", "temp_c": "Температура, °C (35–43)",
    "measured_at": "Момент измерения", "kind": "Вид напоминания", "due_date": "Срок напоминания",
}


def main() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    out = ["# Словарь данных", "", "Сгенерирован из фактической схемы (`schema.sql`) скриптом `tools/gen_dictionary.py`.",
           "Деньги — INTEGER в копейках; даты — TEXT `ГГГГ-ММ-ДД` с `CHECK(date(x) IS NOT NULL)`; время — `ЧЧ:ММ`.", ""]
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        out += [f"## {table}", "", TABLES.get(table, ""), "", "| Поле | Тип | NULL | По умолчанию | Ключ | Смысл |", "|---|---|---|---|---|---|"]
        fks = {r[3]: f"FK → {r[2]}.{r[4]} ({r[6]})" for r in conn.execute(f"PRAGMA foreign_key_list({table})")}
        for _, name, typ, notnull, default, pk in conn.execute(f"PRAGMA table_info({table})"):
            key = "PK" if pk else fks.get(name, "")
            out.append(f"| {name} | {typ or '—'} | {'нет' if notnull or pk else 'да'} | {default if default is not None else ''} "
                       f"| {key} | {FIELDS.get(name, '')} |")
        out.append("")
    out += ["## Представления", "", "- `v_active_appointments` — предстоящие/незавершённые приёмы с ФИО врача и кличкой животного.",
            "- `v_debt_visits` — завершённые приёмы, оплаченные не полностью (долг в копейках).",
            "- `v_animal_revaccination` — ближайший срок ревакцинации животного (по последней вакцинации каждого препарата).", ""]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "словарь_данных.md").write_text("\n".join(out), encoding="utf-8")
    print("docs/словарь_данных.md создан")


if __name__ == "__main__":
    main()
