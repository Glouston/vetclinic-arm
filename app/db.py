"""Подключение к SQLite. Единственное место, где создаётся соединение."""
from __future__ import annotations
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
import sqlite3


from app.errors import DatabaseUnavailable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = Path(os.environ.get("VETCLINIC_DB", ROOT / "vetclinic.db"))


def _ulower(value):
    return value.lower() if isinstance(value, str) else value


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Новое соединение: FK включены, строки — sqlite3.Row, транзакции ручные."""
    path = path or DEFAULT_DB
    try:
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # регистронезависимый поиск по кириллице (встроенный lower() SQLite понимает только ASCII)
        conn.create_function("ulower", 1, _ulower, deterministic=True)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.Error as exc:
        raise DatabaseUnavailable("Не удалось подключиться к базе данных. Проверьте файл БД.") from exc
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE … COMMIT; при любом исключении — ROLLBACK (всё или ничего)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:  # SQLite мог уже откатить транзакцию сам (например, при SQLITE_FULL)
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def is_initialized(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='owners'").fetchone() is not None


def run_script(conn: sqlite3.Connection, script_path: Path) -> None:
    conn.executescript(script_path.read_text(encoding="utf-8"))


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}  # имя таблицы — константа, не ввод


def migrate(conn: sqlite3.Connection, path: str | Path) -> bool:
    """Обновляет БД старой версии без потери данных (перед изменением делается резервная копия).

    v1 → v2: платёж привязан к записи на приём (payments.appointment_id) вместо visit_id —
    это позволяет принимать предоплату до закрытия приёма.
    """
    if "visit_id" not in _columns(conn, "payments"):
        return False
    backup = Path(str(path) + ".bak-before-prepay")
    if not backup.exists() and Path(path).exists():
        shutil.copy2(path, backup)
    ddl = re.search(r"CREATE TABLE IF NOT EXISTS payments \(.*?\n\);", (ROOT / "schema.sql").read_text(encoding="utf-8"),
                    re.S).group(0).replace("IF NOT EXISTS payments", "payments_new")
    conn.execute("PRAGMA foreign_keys = OFF")  # на время пересборки таблицы (вне транзакции)
    try:
        with transaction(conn):
            for obj, name in (("VIEW", "v_debt_visits"), ("TRIGGER", "trg_payment_limit_ins"),
                              ("TRIGGER", "trg_payment_limit_upd")):
                conn.execute(f"DROP {obj} IF EXISTS {name}")
            conn.execute(ddl)
            conn.execute("""INSERT INTO payments_new (id, appointment_id, amount_kopecks, method, status, paid_at)
                            SELECT p.id, v.appointment_id, p.amount_kopecks, p.method, p.status, p.paid_at
                            FROM payments p JOIN visits v ON v.id = p.visit_id""")
            conn.execute("DROP TABLE payments")
            conn.execute("ALTER TABLE payments_new RENAME TO payments")
            if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.IntegrityError("Нарушены внешние ключи после миграции")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    run_script(conn, ROOT / "schema.sql")  # пересоздать индексы, триггеры и представления (IF NOT EXISTS)
    return True


def init_db(path: str | Path | None = None, with_seed: bool = True) -> bool:
    """Создаёт схему (и тестовые данные) ТОЛЬКО если БД пуста. Существующие данные не трогает.

    Возвращает True, если БД была развёрнута.
    """
    conn = connect(path)
    try:
        if is_initialized(conn):
            migrate(conn, path or DEFAULT_DB)
            return False
        run_script(conn, ROOT / "schema.sql")
        if with_seed:
            run_script(conn, ROOT / "seed.sql")
        return True
    finally:
        conn.close()
