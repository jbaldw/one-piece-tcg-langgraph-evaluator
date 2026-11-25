"""Seed the SQLite database. Same as `op-eval seed`; kept as a standalone entry point."""

from op_tcg_evaluator.config import get_settings
from op_tcg_evaluator.db.seed import seed_db

if __name__ == "__main__":
    seed_db(get_settings().db_path)
