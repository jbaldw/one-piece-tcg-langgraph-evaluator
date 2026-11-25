import csv
import sqlite3
import sys
from pathlib import Path

from op_tcg_evaluator.db.connection import get_connection, init_db
from op_tcg_evaluator.db.normalize import ImportReport, canonicalize, card_id_of
from op_tcg_evaluator.db.optcgapi import cache_dir, load_cached

_PRINTING_COLUMNS = {
    "image_id": "card_image_id",
    "name": "card_name",
    "set_id": "set_id",
    "set_name": "set_name",
    "rarity": "rarity",
    "color": "card_color",
    "category": "card_type",
    "cost": "card_cost",
    "power": "card_power",
    "counter": "counter_amount",
    "life": "life",
    "attribute": "attribute",
    "sub_types": "sub_types",
    "card_text": "card_text",
    "market_price": "market_price",
    "inventory_price": "inventory_price",
    "image_url": "card_image",
    "date_scraped": "date_scraped",
}


def load_cards(conn: sqlite3.Connection, rows_by_source: dict[str, list[dict]]) -> ImportReport:
    """Replace all card data with the given optcgapi rows, in one transaction."""
    all_rows = [row for rows in rows_by_source.values() for row in rows]
    cards, report = canonicalize(all_rows)

    with conn:
        conn.execute("DELETE FROM card_printings")
        conn.execute("DELETE FROM card_colors")
        conn.execute("DELETE FROM card_types")

        cols = ", ".join(["card_id", "source", *_PRINTING_COLUMNS])
        marks = ", ".join("?" * (len(_PRINTING_COLUMNS) + 2))
        conn.executemany(
            f"INSERT INTO card_printings ({cols}) VALUES ({marks})",
            [
                (card_id_of(r), source, *(_raw(r.get(k)) for k in _PRINTING_COLUMNS.values()))
                for source, rows in rows_by_source.items()
                for r in rows
            ],
        )

        # Upsert rather than delete, so decks that reference a card keep their foreign keys.
        conn.executemany(
            """
            INSERT INTO cards (id, name, category, color, cost, power, counter, set_code,
                               life, attribute, card_text, types_raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name, category = excluded.category, color = excluded.color,
                cost = excluded.cost, power = excluded.power, counter = excluded.counter,
                set_code = excluded.set_code, life = excluded.life,
                attribute = excluded.attribute, card_text = excluded.card_text,
                types_raw = excluded.types_raw
            """,
            [
                (
                    c.id,
                    c.name,
                    c.category,
                    "/".join(c.colors),
                    c.cost,
                    c.power,
                    c.counter,
                    c.set_code,
                    c.life,
                    c.attribute,
                    c.card_text,
                    c.types_raw,
                )
                for c in cards
            ],
        )
        conn.executemany(
            "INSERT INTO card_colors (card_id, color) VALUES (?, ?)",
            [(c.id, color) for c in cards for color in c.colors],
        )
        conn.executemany(
            "INSERT INTO card_types (card_id, type) VALUES (?, ?)",
            [(c.id, t) for c in cards for t in c.types],
        )
    return report


def _raw(value):
    # Prices stay numeric; everything else is stored as the API's text so nothing is lost.
    if value is None or isinstance(value, float):
        return value
    return str(value)


def write_report(report: ImportReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["card_id", "field", "chosen", "alternatives"])
        for c in report.conflicts:
            writer.writerow([c.card_id, c.field, c.chosen, " | ".join(c.alternatives)])
        for card_id, reason in report.skipped:
            writer.writerow([card_id, "SKIPPED", reason, ""])
        for t in sorted(report.guessed_types):
            writer.writerow(["", "GUESSED_TYPE", t, ""])
        for card_id, field, reason in report.suspicious:
            writer.writerow([card_id, "SUSPICIOUS_TEXT", field, reason])


def seed_db(db_path: Path) -> None:
    init_db(db_path)
    src = cache_dir(db_path)
    rows_by_source = load_cached(src)
    with get_connection(db_path) as conn:
        report = load_cards(conn, rows_by_source)
        printings = conn.execute("SELECT COUNT(*) FROM card_printings").fetchone()[0]
        cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    report_path = src / "import_report.csv"
    write_report(report, report_path)
    print(
        f"Loaded {printings} printings into {cards} cards. "
        f"{len(report.conflicts)} field conflicts resolved, {len(report.skipped)} cards skipped, "
        f"{len(report.guessed_types)} types inferred. Details: {report_path}"
    )
    if report.suspicious:
        # This text reaches generation prompts, so it gets its own line instead of a count.
        print(
            f"WARNING: {len(report.suspicious)} card fields look like they contain text aimed "
            f"at an LLM (SUSPICIOUS_TEXT rows in {report_path}). Review them before generating.",
            file=sys.stderr,
        )
