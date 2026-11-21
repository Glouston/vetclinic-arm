"""Отчёты: расчёты и граничные даты, XLSX, напоминания, история цен, индексы."""
from __future__ import annotations
from openpyxl import load_workbook

from app.reports import export, queries
from app.repositories import catalog
from app.services import reminders
from tests.conftest import TODAY


def test_t22_operational_report(conn):
    """T-22 | Оперативный отчёт: приёмы на дату по статусу | дата сегодня, статусы все/конкретный/нет данных |
    число строк = SQL COUNT, итог = число записей, пустой результат помечен."""
    r = queries.operational(conn, TODAY, None)
    expected = conn.execute("SELECT COUNT(*) FROM appointments WHERE appt_date = ?", (TODAY,)).fetchone()[0]
    assert len(r.rows) == expected > 0 and r.total[1] == expected
    only = queries.operational(conn, TODAY, "подтверждён")
    assert all(row[5] == "подтверждён" for row in only.rows)
    assert queries.operational(conn, "1999-01-01", None).empty


def test_t23_revenue_report_boundaries(conn):
    """T-23 | Сводный отчёт: итоги и границы периода | период = день одного платежа; период на день раньше |
    границы включены; итог = сумма строк; сумма всех платежей за весь период совпадает с SQL."""
    pay = conn.execute("SELECT date(paid_at) d, amount_kopecks a FROM payments WHERE status='оплачен' "
                       "ORDER BY paid_at LIMIT 1").fetchone()
    day = queries.revenue(conn, pay["d"], pay["d"], None)
    assert not day.empty and day.total[3] >= pay["a"]
    assert sum(r[3] for r in day.rows) == day.total[3]
    expected = conn.execute("SELECT SUM(CASE status WHEN 'оплачен' THEN amount_kopecks ELSE -amount_kopecks END) "
                            "FROM payments WHERE status IN ('оплачен', 'возврат')").fetchone()[0]  # возвраты вычитаются
    assert queries.revenue(conn, "2000-01-01", "2100-01-01", None).total[3] == expected
    assert queries.revenue(conn, "2000-01-01", "2000-01-02", None).empty
    cat = queries.revenue(conn, "2000-01-01", "2100-01-01", "Приём")
    assert cat.total[3] <= expected and all(r[1] in ("Первичный приём", "Повторный приём", "Консультация кардиолога") for r in cat.rows)


def test_t24_problem_report(conn):
    """T-24 | Проблемный отчёт: просроченная ревакцинация и долг старше N дней | порог 0/30/10000 дней, режим И/ИЛИ |
    больший порог даёт не больше строк; режим «И» ⊆ «ИЛИ»; порог 10000 — без долгов."""
    any_ = queries.problem(conn, TODAY, 0, both=False)
    assert not any_.empty
    strict = queries.problem(conn, TODAY, 30, both=False)
    assert len(strict.rows) <= len(any_.rows)
    both = queries.problem(conn, TODAY, 0, both=True)
    assert {r[0:3].__str__() for r in both.rows} <= {r[0:3].__str__() for r in any_.rows}
    assert all(r[7] == "Ревакцинация + долг" for r in both.rows)
    no_debts = queries.problem(conn, TODAY, 10000, both=False)
    assert all(r[7] == "Ревакцинация" for r in no_debts.rows)
    assert any_.total[1] == len(any_.rows)


def test_t25_xlsx_export_keeps_conditions_and_cyrillic(conn, tmp_path):
    """T-25 | Выгрузка XLSX с условиями отбора и кириллицей | export_xlsx сводного отчёта, чтение файла |
    в файле заголовок, условия, итог и числовая сумма в рублях."""
    r = queries.revenue(conn, "2026-01-01", "2026-12-31", "Приём")
    path = tmp_path / "r.xlsx"
    export.export_xlsx(r, path)
    ws = load_workbook(path).active
    text = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    assert "Сводный отчёт: выручка по врачам и услугам" in text
    assert "Категория услуг:" in text and "Приём" in text and "01.01.2026" in text
    assert "ИТОГО" in text
    assert any(isinstance(v, (int, float)) or v.__class__.__name__ == "Decimal" for v in text)
    pdf = tmp_path / "r.pdf"
    export.export_report_pdf(r, pdf)
    assert pdf.stat().st_size > 1000


def test_t26_reminders_generation_idempotent(conn):
    """T-26 | Генерация напоминаний без дублей | вызвать generate дважды | второй вызов создаёт 0;
    просроченные ревакцинации отмечены «просрочено»."""
    reminders.generate(conn, TODAY)
    assert reminders.generate(conn, TODAY) == 0
    rows = reminders.list_reminders(conn, "просрочено", TODAY)
    assert rows and all(r.due_date < TODAY for r in rows)


def test_t27_price_history(conn):
    """T-27 | История цен: новая версия, а не правка | add_price_version | старая закрыта днём раньше,
    действующая цена на разные даты разная; нельзя добавить версию «в прошлое»."""
    import pytest
    from app.errors import UserError
    catalog.add_price_version(conn, 2, 80000, "2026-11-01")
    assert catalog.current_price(conn, 2, "2026-10-31") == 2500
    assert catalog.current_price(conn, 2, "2026-11-01") == 80000
    hist = catalog.price_history(conn, 2)
    assert hist[0].valid_to is None and hist[1].valid_to == "2026-10-31"
    with pytest.raises(UserError):
        catalog.add_price_version(conn, 2, 90000, "2026-10-01")


def test_t28_index_used_in_query_plan(conn):
    """T-28 | Индексы по дате и статусу используются | EXPLAIN QUERY PLAN | в плане есть SEARCH … USING INDEX."""
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM appointments WHERE appt_date = '2026-10-28'"))
    assert "ix_appointments_date" in plan
    plan2 = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM stock_batches WHERE expiry_date < '2026-12-01'"))
    assert "ix_stock_batches_expiry" in plan2
