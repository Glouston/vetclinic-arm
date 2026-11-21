"""Выполняет все запросы из queries.sql на свежей БД (schema + seed), печатает число строк и EXPLAIN-планы индексов.

Запуск: python tools/check_queries.py
"""
from __future__ import annotations
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARAMS = {"s": None, "species": None, "sex": None, "today": "2026-10-28", "df": "2026-09-01", "dt": "2026-12-31",
          "status": None, "vet": None, "animal_id": 1, "days": None, "f": "2026-01-01", "t": "2026-12-31", "c": None,
          "min": 1, "d": "2026-10-28", "n": 30, "vet_id": 1, "service_id": 2, "qty": 1, "batch_id": 1}


def main() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    conn.executescript((ROOT / "seed.sql").read_text(encoding="utf-8"))
    text = (ROOT / "queries.sql").read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^-- (?=Q\d\d \|)", text)[1:]
    for block in blocks:
        qid = block[:3]
        sql_lines = [ln for ln in block.splitlines()[1:] if not ln.startswith("--")]
        sql = "\n".join(sql_lines).strip()
        sql = re.split(r"\n-- -{5,}", sql)[0].strip()
        params = dict(PARAMS)
        if qid == "Q14":
            params["d"], params["t"], params["animal_id"] = "2031-01-01", "10:00", 1
        if qid == "Q16":
            params["animal_id"] = 30
        cur = conn.execute(sql, {k: v for k, v in params.items() if f":{k}" in sql})
        n = len(cur.fetchall()) if cur.description else cur.rowcount
        print(f"{qid}: OK, строк: {n}")
    print("\nEXPLAIN QUERY PLAN (индексы):")
    for q in ("SELECT * FROM appointments WHERE appt_date = '2026-10-28'",
              "SELECT * FROM appointments WHERE status = 'подтверждён'",
              "SELECT * FROM stock_batches WHERE expiry_date < '2026-12-01'"):
        print(" ", q)
        for row in conn.execute("EXPLAIN QUERY PLAN " + q):
            print("    ", row[3])
    if len(blocks) < 12:
        sys.exit("Запросов меньше 12")


if __name__ == "__main__":
    main()
