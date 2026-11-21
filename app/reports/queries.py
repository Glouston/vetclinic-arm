"""Три отчёта (ТЗ п.9.1). Все расчёты — SQL; Python только оформляет результат."""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass, field

# виды колонок: text | int | money (копейки) | date
Column = tuple[str, str]


@dataclass
class ReportResult:
    title: str
    params: list[tuple[str, str]]          # условия отбора — попадают в XLSX/печать
    columns: list[Column]
    rows: list[list]
    total: list | None = None              # итоговая строка
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.rows


def operational(conn: sqlite3.Connection, day: str, status: str | None) -> ReportResult:
    """1. Оперативный: приёмы на дату по статусам."""
    rows = conn.execute(
        """SELECT a.appt_time, an.name, o.full_name, v.full_name, s.name, a.status, a.price_kopecks
           FROM appointments a
           JOIN animals an ON an.id = a.animal_id JOIN owners o ON o.id = an.owner_id
           JOIN vets v ON v.id = a.vet_id JOIN services s ON s.id = a.service_id
           WHERE a.appt_date = :d AND (:st IS NULL OR a.status = :st)
           ORDER BY a.appt_time, v.full_name""", {"d": day, "st": status or None}).fetchall()
    totals = conn.execute(
        """SELECT COUNT(*), COALESCE(SUM(price_kopecks), 0) FROM appointments
           WHERE appt_date = :d AND (:st IS NULL OR status = :st)""", {"d": day, "st": status or None}).fetchone()
    return ReportResult(
        "Оперативный отчёт: приёмы на дату",
        [("Дата", day), ("Статус", status or "все")],
        [("Время", "text"), ("Животное", "text"), ("Владелец", "text"), ("Врач", "text"),
         ("Услуга", "text"), ("Статус", "text"), ("Сумма", "money")],
        [list(r) for r in rows],
        ["Итого записей:", totals[0], "", "", "", "", totals[1]] if rows else None)


def revenue(conn: sqlite3.Connection, date_from: str, date_to: str, category: str | None) -> ReportResult:
    """2. Сводный: выручка по врачам и услугам за период.

    Выручка = оплаченные платежи минус возвраты, дата — по paid_at (включая обе границы периода).
    """
    p = {"f": date_from, "t": date_to, "c": category or None}
    rows = conn.execute(
        """SELECT v.full_name, s.name, COUNT(DISTINCT a.id),
                  SUM(CASE pay.status WHEN 'оплачен' THEN pay.amount_kopecks ELSE -pay.amount_kopecks END)
           FROM payments pay
           JOIN appointments a ON a.id = pay.appointment_id
           JOIN vets v ON v.id = a.vet_id JOIN services s ON s.id = a.service_id
           WHERE pay.status IN ('оплачен', 'возврат')
             AND date(pay.paid_at) BETWEEN :f AND :t AND (:c IS NULL OR s.category = :c)
           GROUP BY v.id, s.id ORDER BY v.full_name, 4 DESC""", p).fetchall()
    tot = conn.execute(
        """SELECT COUNT(DISTINCT a.id),
                  COALESCE(SUM(CASE pay.status WHEN 'оплачен' THEN pay.amount_kopecks ELSE -pay.amount_kopecks END), 0)
           FROM payments pay JOIN appointments a ON a.id = pay.appointment_id
           JOIN services s ON s.id = a.service_id
           WHERE pay.status IN ('оплачен', 'возврат')
             AND date(pay.paid_at) BETWEEN :f AND :t AND (:c IS NULL OR s.category = :c)""", p).fetchone()
    return ReportResult(
        "Сводный отчёт: выручка по врачам и услугам",
        [("Период с", date_from), ("по", date_to), ("Категория услуг", category or "все")],
        [("Врач", "text"), ("Услуга", "text"), ("Записей с оплатой", "int"), ("Выручка", "money")],
        [list(r) for r in rows],
        ["ИТОГО", "", tot[0], tot[1]] if rows else None,
        note="Выручка = оплаченные платежи (включая предоплату) минус возвраты по дате оплаты, обе границы периода включены.")


PROBLEM_NOTE = ("Просроченная ревакцинация: ближайший срок ревакцинации (по последней вакцинации каждого препарата) "
                "раньше контрольной даты. Долг: завершённый приём, оплаченный не полностью, старше порога дней "
                "на контрольную дату.")


def problem(conn: sqlite3.Connection, control_date: str, days: int, both: bool = False) -> ReportResult:
    """3. Проблемный: животные с просроченной ревакцинацией и/или долгом старше N дней."""
    rows = conn.execute(
        """WITH overdue AS (
               SELECT animal_id, next_due_date,
                      CAST(julianday(:d) - julianday(next_due_date) AS INTEGER) AS days_over
               FROM v_animal_revaccination WHERE next_due_date < :d),
           debts AS (
               SELECT animal_id, SUM(debt_kopecks) AS debt,
                      MAX(CAST(julianday(:d) - julianday(appt_date) AS INTEGER)) AS oldest
               FROM v_debt_visits WHERE julianday(:d) - julianday(appt_date) > :n GROUP BY animal_id)
           SELECT an.name, o.full_name, o.phone, od.next_due_date, od.days_over, db.debt, db.oldest,
                  CASE WHEN od.animal_id IS NOT NULL AND db.animal_id IS NOT NULL THEN 'Ревакцинация + долг'
                       WHEN od.animal_id IS NOT NULL THEN 'Ревакцинация' ELSE 'Долг' END
           FROM animals an JOIN owners o ON o.id = an.owner_id
           LEFT JOIN overdue od ON od.animal_id = an.id LEFT JOIN debts db ON db.animal_id = an.id
           WHERE (:both = 0 AND (od.animal_id IS NOT NULL OR db.animal_id IS NOT NULL))
              OR (:both = 1 AND od.animal_id IS NOT NULL AND db.animal_id IS NOT NULL)
           ORDER BY (od.animal_id IS NOT NULL AND db.animal_id IS NOT NULL) DESC, an.name""",
        {"d": control_date, "n": days, "both": int(both)}).fetchall()
    return ReportResult(
        "Проблемный отчёт: ревакцинация и задолженность",
        [("Контрольная дата", control_date), ("Порог долга, дней", str(days)),
         ("Условие", "оба сразу (И)" if both else "любое из двух (ИЛИ)")],
        [("Животное", "text"), ("Владелец", "text"), ("Телефон", "text"), ("Ревакцинация до", "date"),
         ("Просрочено, дн.", "int"), ("Долг", "money"), ("Старейший долг, дн.", "int"), ("Проблема", "text")],
        [list(r) for r in rows],
        ["ИТОГО животных:", len(rows), "", "", "", sum(r[5] or 0 for r in rows), "", ""] if rows else None,
        note=PROBLEM_NOTE)
