from pathlib import Path

from op_tcg_evaluator.db.connection import init_db


def seed_db(db_path: Path) -> None:
    init_db(db_path)
    # TODO: load card data (source TBD) and insert into the cards table.
    print("Seeding not implemented yet; schema is initialized.")
