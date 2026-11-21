"""Записи на приём: выборки для списка, дашборда и расписания."""
from __future__ import annotations
from app.models import Appointment, DashboardStats
from app.repositories.clients import _like
from app.util import today_iso

WORK_SLOTS = [f"{h:02d}:{m:02d}" for h in range(9, 18) for m in (0, 30)]  # 09:00 … 17:30

_SELECT = """
SELECT a.id, a.appt_date, a.appt_time, a.status, a.price_kopecks,
       an.id AS animal_id, an.name AS animal_name, o.full_name AS owner_name, o.phone AS owner_phone,
       v.id AS vet_id, v.full_name AS vet_name, s.id AS service_id, s.name AS service_name,
       vi.id AS visit_id,
       COALESCE((SELECT SUM(CASE p.status WHEN 'оплачен' THEN p.amount_kopecks
                                          WHEN 'возврат' THEN -p.amount_kopecks ELSE 0 END)
                 FROM payments p WHERE p.appointment_id = a.id), 0) AS paid_kopecks
FROM appointments a
JOIN animals an ON an.id = a.animal_id
JOIN owners o ON o.id = an.owner_id
JOIN vets v ON v.id = a.vet_id
JOIN services s ON s.id = a.service_id
LEFT JOIN visits vi ON vi.appointment_id = a.id
"""


def list_appointments(conn, date_from: str | None = None, date_to: str | None = None, status: str | None = None,
                      vet_id: int | None = None, search: str | None = None, animal_id: int | None = None,
                      newest_first: bool = False) -> list[Appointment]:
    order = "DESC" if newest_first else "ASC"
    rows = conn.execute(
        _SELECT + f"""
        WHERE (:df IS NULL OR a.appt_date >= :df) AND (:dt IS NULL OR a.appt_date <= :dt)
          AND (:status IS NULL OR a.status = :status)
          AND (:vet IS NULL OR a.vet_id = :vet)
          AND (:animal IS NULL OR a.animal_id = :animal)
          AND (:s IS NULL OR ulower(an.name) LIKE :s ESCAPE '\\' OR ulower(o.full_name) LIKE :s ESCAPE '\\')
        ORDER BY a.appt_date {order}, a.appt_time {order}""",
        {"df": date_from, "dt": date_to, "status": status or None, "vet": vet_id, "animal": animal_id,
         "s": _like(search)}).fetchall()
    return [Appointment.from_row(r) for r in rows]


def get_appointment(conn, appointment_id: int) -> Appointment | None:
    r = conn.execute(_SELECT + " WHERE a.id = ?", (appointment_id,)).fetchone()
    return Appointment.from_row(r) if r else None


def upcoming(conn, today: str | None = None, limit: int = 8) -> list[Appointment]:
    """Ближайшие незавершённые приёмы начиная с сегодняшнего дня."""
    rows = conn.execute(
        _SELECT + """ WHERE a.appt_date >= :today AND a.status IN ('запланирован', 'подтверждён')
                      ORDER BY a.appt_date, a.appt_time LIMIT :n""",
        {"today": today or today_iso(), "n": limit}).fetchall()
    return [Appointment.from_row(r) for r in rows]


def busy_times(conn, vet_id: int, appt_date: str) -> set[str]:
    rows = conn.execute(
        "SELECT appt_time FROM appointments WHERE vet_id = ? AND appt_date = ? AND status <> 'отменён'",
        (vet_id, appt_date))
    return {r[0] for r in rows}


def slot_is_free(conn, vet_id: int, appt_date: str, appt_time: str) -> bool:
    return appt_time not in busy_times(conn, vet_id, appt_date)


def dashboard_stats(conn, today: str | None = None) -> DashboardStats:
    today = today or today_iso()
    r = conn.execute(
        """SELECT
             (SELECT COUNT(*) FROM appointments WHERE appt_date = :t AND status <> 'отменён'),
             (SELECT COUNT(*) FROM v_debt_visits),
             (SELECT COUNT(*) FROM v_animal_revaccination WHERE next_due_date < :t),
             (SELECT COUNT(*) FROM stock_batches
               WHERE qty > 0 AND expiry_date >= :t AND expiry_date <= date(:t, '+30 days'))""",
        {"t": today}).fetchone()
    return DashboardStats(*r)
