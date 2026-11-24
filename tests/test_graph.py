from op_tcg_evaluator.graph import EvaluatorState, build_graph
from op_tcg_evaluator.models import Decklist, EvaluationResult

FAKE_RESULT = EvaluationResult(score=70, strengths=["s"], weaknesses=["w"], suggestions=["x"])


def _fake_evaluate(state: EvaluatorState) -> dict:
    return {"evaluation": FAKE_RESULT}


def _run(raw: str) -> EvaluatorState:
    graph = build_graph(evaluate_node=_fake_evaluate)
    return EvaluatorState.model_validate(graph.invoke(EvaluatorState(raw_decklist=raw)))


def test_valid_decklist_reaches_evaluate():
    lines = ["OP01-001"] + [f"4xOP01-{i:03d}" for i in range(2, 14)] + ["2xOP01-014"]
    result = _run("\n".join(lines))
    assert result.errors == []
    assert result.evaluation == FAKE_RESULT


def test_to_text_round_trips_through_parser():
    deck = Decklist(
        leader_id="OP01-001",
        cards=[{"card_id": f"OP01-{i:03d}", "quantity": 4} for i in range(2, 14)]
        + [{"card_id": "OP01-014", "quantity": 2}],
    )
    result = _run(deck.to_text())
    assert result.errors == []
    assert result.decklist == deck


def test_unparseable_line_stops_graph():
    result = _run("OP01-001\nnot a card line")
    assert result.evaluation is None
    assert "could not parse" in result.errors[0]


def test_invalid_deck_stops_graph():
    result = _run("OP01-001\n4xOP01-002")
    assert result.evaluation is None
    assert any("50 cards" in e for e in result.errors)
