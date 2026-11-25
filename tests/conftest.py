from contextlib import closing

import pytest

from op_tcg_evaluator.db.connection import get_connection, init_db
from op_tcg_evaluator.rules import CardLookup

# Red leader OP01-001 with legal Red characters OP01-002..OP01-020, plus an off-color
# character and a second (Green) leader to trip the rules.
_CARDS = [
    ("OP01-001", "Roronoa Zoro", "Leader", "Red", None, 5000, None, 5),
    *[
        (f"OP01-{i:03d}", f"Red Card {i}", "Character", "Red", 2, 3000, 1000, None)
        for i in range(2, 21)
    ],
    ("OP01-030", "Green Card", "Character", "Green", 3, 4000, 1000, None),
    ("OP02-001", "Green Leader", "Leader", "Green", None, 5000, None, 4),
]


@pytest.fixture(scope="session")
def cards(tmp_path_factory) -> CardLookup:
    db = tmp_path_factory.mktemp("cards") / "cards.db"
    init_db(db)
    with closing(get_connection(db)) as conn, conn:
        conn.executemany(
            "INSERT INTO cards (id, name, category, color, cost, power, counter, life) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            _CARDS,
        )
        conn.executemany(
            "INSERT INTO card_colors (card_id, color) VALUES (?, ?)",
            [(c[0], c[3]) for c in _CARDS],
        )
        conn.execute("INSERT INTO card_types (card_id, type) VALUES ('OP01-001', 'Straw Hat Crew')")
    return CardLookup(db)
