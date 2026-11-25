import pytest

from op_tcg_evaluator.graph import EvaluatorState, GeneratorState, build_graph
from op_tcg_evaluator.graph.nodes import build_generation_prompt, check_deck
from op_tcg_evaluator.models import DeckDraft
from op_tcg_evaluator.rules import CardLookup, check_deck_rules

LEADER = "OP01-001"
LEGAL_IDS = [f"OP01-{i:03d}" for i in range(2, 14)] + ["OP01-014"]


def test_legal_pool_is_leader_colored_non_leaders(cards):
    leader = cards.get_many([LEADER])[LEADER]
    pool = [c.id for c in cards.legal_pool(leader)]
    assert pool == [f"OP01-{i:03d}" for i in range(2, 21)]


def test_legal_deck_has_no_rule_errors(cards):
    assert check_deck_rules(LEADER, LEGAL_IDS, cards) == []


@pytest.mark.parametrize(
    ("leader", "card_ids", "expected"),
    [
        (LEADER, ["OP01-030"], "OP01-030 (Green Card) is Green, but leader OP01-001"),
        (LEADER, ["OP09-999"], "OP09-999 is not in the card database"),
        (LEADER, ["OP02-001"], "OP02-001 (Green Leader) is a Leader and cannot be in the main"),
        ("OP01-002", ["OP01-003"], "leader_id: OP01-002 (Red Card 2) is a Character"),
        ("OP09-001", ["OP01-003"], "leader_id: OP09-001 is not in the card database"),
    ],
)
def test_rule_violations_are_reported(cards, leader, card_ids, expected):
    errors = check_deck_rules(leader, card_ids, cards)
    assert len(errors) == 1
    assert errors[0].startswith(expected)


def test_generator_feeds_color_errors_back(cards):
    ids = LEGAL_IDS[:-1] + ["OP01-030"]
    draft = DeckDraft(
        leader_id=LEADER,
        cards=[{"card_id": cid, "quantity": 4} for cid in ids[:-1]]
        + [{"card_id": "OP01-030", "quantity": 2}],
    )
    result = check_deck(GeneratorState(leader_id=LEADER, attempts=1, draft=draft), cards)
    assert any(e.startswith("OP01-030 (Green Card) is Green") for e in result["errors"])
    assert "decklist" not in result


def test_prompt_lists_leader_and_legal_pool(cards):
    leader = cards.get_many([LEADER])[LEADER]
    prompt = build_generation_prompt(
        GeneratorState(leader_id=LEADER), leader, cards.legal_pool(leader)
    )
    assert "Color: Red" in prompt
    assert "Types: Straw Hat Crew" in prompt
    assert "OP01-002 | Red Card 2 | Character | cost 2 | 3000 power | +1000 counter" in prompt
    assert "OP01-030" not in prompt


def test_evaluator_rejects_off_color_deck(cards):
    lines = [LEADER] + [f"4x{cid}" for cid in LEGAL_IDS[:-1]] + ["2xOP01-030"]
    graph = build_graph(evaluate_node=lambda state: pytest.fail("should not evaluate"), cards=cards)
    result = EvaluatorState.model_validate(
        graph.invoke(EvaluatorState(raw_decklist="\n".join(lines)))
    )
    assert result.evaluation is None
    assert any("OP01-030 (Green Card) is Green" in e for e in result.errors)


def test_missing_database_has_setup_hint(tmp_path):
    with pytest.raises(FileNotFoundError, match="op-eval seed"):
        CardLookup(tmp_path / "missing.db")
