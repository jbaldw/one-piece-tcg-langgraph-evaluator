import sqlite3
from importlib.resources import files
from pathlib import Path

from op_tcg_evaluator.models import Card


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # SQLite leaves foreign keys off by default, per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    schema = files("op_tcg_evaluator.db").joinpath("schema.sql").read_text(encoding="utf-8")
    with get_connection(db_path) as conn:
        conn.executescript(schema)


def card_from_row(row: sqlite3.Row) -> Card:
    return Card.model_validate(dict(row))
