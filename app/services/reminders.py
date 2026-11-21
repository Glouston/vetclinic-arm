"""Напоминания: оперативный список и генерация по вакцинациям и долгам."""
from __future__ import annotations
import sqlite3

from app.db import transaction
from app.errors import UserError
from app.models import Reminder
from app.util import today_iso


def list_reminders(conn: sqlite3.Connection, status: str | None = None, today: str | None = None) -> list[Reminder]:
    """Список; статус «запланировано» с прошедшим сроком показывается как «просрочено»."""
    rows = conn.execute(
        """SELECT r.id, r.animal_id, an.name AS animal_name, o.full_name AS owner_name, r.kind, r.due_date,
                  CASE WHEN r.status = 'запланировано' AND r.due_date < :t THEN 'просрочено' ELSE r.status END AS status
           FROM reminders r JOIN animals an ON an.id = r.animal_id JOIN owners o ON o.id = an.owner_id
           WHERE (:st IS NULL OR (CASE WHEN r.status = 'запланировано' AND r.due_date < :t
                                       THEN 'просрочено' ELSE r.status END) = :st)
           ORDER BY (r.status = 'выполнено'), r.due_date""", {"t": today or today_iso(), "st": status or None}).fetchall()
    return [Reminder.from_row(r) for r in rows]


def mark_done(conn: sqlite3.Connection, reminder_id: int) -> None:
    cur = conn.execute("UPDATE reminders SET status = 'выполнено' WHERE id = ?", (reminder_id,))
    if cur.rowcount == 0:
        raise UserError("Напоминание не найдено.")


def generate(conn: sqlite3.Connection, today: str | None = None) -> int:
    """Создаёт недостающие напоминания (повторный вызов дубликатов не создаёт: UNIQUE + OR IGNORE).

    * ревакцинация — для животных, у которых срок прошёл или наступит в ближайшие 30 дней;
    * оплата — по неоплаченным завершённым приёмам, срок = дата приёма + 14 дней.
    """
    today = today or today_iso()
    with transaction(conn):
        before = conn.total_changes
        conn.execute(
            """INSERT OR IGNORE INTO reminders (animal_id, kind, due_date, status)
               SELECT animal_id, 'ревакцинация', next_due_date,
                      CASE WHEN next_due_date < :t THEN 'просрочено' ELSE 'запланировано' END
               FROM v_animal_revaccination WHERE next_due_date <= date(:t, '+30 days')""", {"t": today})
        conn.execute(
            """INSERT OR IGNORE INTO reminders (animal_id, kind, due_date, status)
               SELECT animal_id, 'оплата', date(appt_date, '+14 days'),
                      CASE WHEN date(appt_date, '+14 days') < :t THEN 'просрочено' ELSE 'запланировано' END
               FROM v_debt_visits""", {"t": today})
        created = conn.total_changes - before
        conn.execute("UPDATE reminders SET status = 'просрочено' WHERE status = 'запланировано' AND due_date < ?",
                     (today,))
    return created
