import pytest
from pydantic import ValidationError

from op_tcg_evaluator.models import Card, Decklist


def _entries(*quantities: int) -> list[dict]:
    return [{"card_id": f"OP01-{i:03d}", "quantity": q} for i, q in enumerate(quantities, 2)]


def test_valid_decklist():
    deck = Decklist(leader_id="OP01-001", cards=_entries(*[4] * 12, 2))
    assert sum(e.quantity for e in deck.cards) == 50


def test_wrong_deck_size_rejected():
    with pytest.raises(ValidationError, match="50 cards"):
        Decklist(leader_id="OP01-001", cards=_entries(4, 4))


def test_too_many_copies_rejected():
    with pytest.raises(ValidationError):
        Decklist(leader_id="OP01-001", cards=_entries(5, *[4] * 11, 1))


def test_duplicate_card_ids_rejected():
    cards = _entries(*[4] * 12, 2)
    cards[-1]["card_id"] = cards[0]["card_id"]
    with pytest.raises(ValidationError, match="only once"):
        Decklist(leader_id="OP01-001", cards=cards)


def test_deck_card_ids_are_strict():
    cards = _entries(*[4] * 12, 2)
    cards[0]["card_id"] = "op01-002"
    with pytest.raises(ValidationError, match="pattern"):
        Decklist(leader_id="OP01-001", cards=cards)


def test_to_text_format():
    deck = Decklist(leader_id="OP01-001", cards=_entries(*[4] * 12, 2))
    lines = deck.to_text().splitlines()
    assert lines[0] == "OP01-001"
    assert lines[1] == "4xOP01-002"
    assert len(lines) == 14


def test_card_id_format():
    with pytest.raises(ValidationError):
        Card(id="bad", name="X", category="Leader", color="Red")
