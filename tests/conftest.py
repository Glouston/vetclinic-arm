from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.qt_env import ensure_qt_plugins_visible  # noqa: E402

ensure_qt_plugins_visible()  # до создания QApplication в pytest-qt

TODAY = "2026-10-28"  # дата, на которую сформирован seed.sql


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "vet.db"
    assert db.init_db(path) is True
    return path


@pytest.fixture
def conn(db_path):
    c = db.connect(db_path)
    yield c
    c.close()


@pytest.fixture
def empty_conn(tmp_path):
    """БД только со схемой, без данных."""
    path = tmp_path / "empty.db"
    db.init_db(path, with_seed=False)
    c = db.connect(path)
    yield c
    c.close()
