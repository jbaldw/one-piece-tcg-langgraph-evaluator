"""Deck rules that need real card data, checked against the SQLite card database."""

from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

from op_tcg_evaluator.db.connection import get_connection
from op_tcg_evaluator.models import Card, CardCategory

_CARD_QUERY = """
    SELECT c.*, (SELECT group_concat(type, '|') FROM card_types t WHERE t.card_id = c.id)
           AS types
    FROM cards c
"""


class CardLookup:
    # Opens a connection per query: LangGraph may run nodes on worker threads, and a
    # sqlite3 connection may only be used on the thread that created it.
    def __init__(self, db_path: Path):
        if not db_path.exists():
            raise FileNotFoundError(
                f"no card database at {db_path}; run `op-eval init-db`, `op-eval fetch-cards`, "
                "and `op-eval seed`"
            )
        self.db_path = db_path

    def _query(self, where: str, params: Iterable) -> list[Card]:
        with closing(get_connection(self.db_path)) as conn:
            rows = conn.execute(f"{_CARD_QUERY} WHERE {where} ORDER BY c.id", list(params))
            return [_to_card(dict(row)) for row in rows]

    def get_many(self, card_ids: Iterable[str]) -> dict[str, Card]:
        ids = list(dict.fromkeys(card_ids))
        if not ids:
            return {}
        cards = self._query(f"c.id IN ({', '.join('?' * len(ids))})", ids)
        return {card.id: card for card in cards}

    def image_urls(self, card_ids: Iterable[str]) -> dict[str, str]:
        """One image URL per card, preferring the base printing over parallels and reprints."""
        ids = list(dict.fromkeys(card_ids))
        if not ids:
            return {}
        with closing(get_connection(self.db_path)) as conn:
            rows = conn.execute(
                f"""
                SELECT card_id, image_url FROM card_printings
                WHERE card_id IN ({", ".join("?" * len(ids))}) AND image_url != ''
                ORDER BY card_id, image_id != card_id, image_id
                """,
                ids,
            ).fetchall()
        urls: dict[str, str] = {}
        for card_id, url in rows:
            urls.setdefault(card_id, url)
        return urls

    def legal_pool(self, leader: Card) -> list[Card]:
        """Every non-Leader card whose color is one of the leader's colors."""
        colors = leader.colors
        return self._query(
            "c.category != 'Leader' AND c.id IN (SELECT card_id FROM card_colors "
            f"WHERE color IN ({', '.join('?' * len(colors))}))",
            colors,
        )


def _to_card(row: dict) -> Card:
    row["types"] = row["types"].split("|") if row["types"] else []
    return Card.model_validate(row)


def leader_problem(leader_id: str, cards: dict[str, Card]) -> str | None:
    leader = cards.get(leader_id)
    if leader is None:
        return f"leader_id: {leader_id} is not in the card database"
    if leader.category != CardCategory.LEADER:
        return f"leader_id: {leader_id} ({leader.name}) is a {leader.category}, not a Leader"
    return None


def check_deck_rules(leader_id: str, card_ids: Iterable[str], lookup: CardLookup) -> list[str]:
    """Return one error per rule broken, worded so Claude can fix the deck from it."""
    card_ids = list(card_ids)
    cards = lookup.get_many([leader_id, *card_ids])
    errors = []
    problem = leader_problem(leader_id, cards)
    if problem:
        errors.append(problem)
    leader = None if problem else cards[leader_id]

    for card_id in dict.fromkeys(card_ids):
        card = cards.get(card_id)
        if card is None:
            errors.append(f"{card_id} is not in the card database")
        elif card.category == CardCategory.LEADER:
            errors.append(f"{card_id} ({card.name}) is a Leader and cannot be in the main deck")
        elif leader is not None and not set(card.colors) & set(leader.colors):
            errors.append(
                f"{card_id} ({card.name}) is {card.color}, but leader {leader.id} "
                f"({leader.name}) is {leader.color}"
            )
    return errors
