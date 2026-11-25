from op_tcg_evaluator.graph import (
    EvaluatorState,
    GeneratorState,
    PipelineState,
    build_pipeline_graph,
)
from op_tcg_evaluator.models import DeckDraft, EvaluationResult

LEADER = "OP01-001"
FAKE_RESULT = EvaluationResult(score=70, strengths=["s"], weaknesses=["w"], suggestions=["x"])

VALID = DeckDraft(
    leader_id=LEADER,
    cards=[{"card_id": f"OP01-{i:03d}", "quantity": 4} for i in range(2, 14)]
    + [{"card_id": "OP01-014", "quantity": 2}],
)
TOO_SMALL = DeckDraft(leader_id=LEADER, cards=[{"card_id": "OP01-002", "quantity": 4}])


def _fake_generator(replies: list[DeckDraft]):
    remaining = list(replies)

    def node(state: GeneratorState) -> dict:
        return {"attempts": state.attempts + 1, "draft": remaining.pop(0), "errors": []}

    return node


def _run(replies: list[DeckDraft], cards) -> tuple[PipelineState, list[EvaluatorState]]:
    evaluated: list[EvaluatorState] = []

    def fake_evaluate(state: EvaluatorState) -> dict:
        evaluated.append(state)
        return {"evaluation": FAKE_RESULT}

    graph = build_pipeline_graph(
        generate_node=_fake_generator(replies), evaluate_node=fake_evaluate, cards=cards
    )
    result = PipelineState.model_validate(graph.invoke(PipelineState(leader_id=LEADER)))
    return result, evaluated


def test_generates_then_evaluates(cards):
    result, evaluated = _run([TOO_SMALL, VALID], cards)
    assert result.generation_attempts == 2
    assert result.decklist.to_text() == VALID.to_text()
    assert result.evaluation == FAKE_RESULT
    assert result.errors == []
    assert len(evaluated) == 1
    assert evaluated[0].decklist.to_text() == VALID.to_text()


def test_failed_generation_skips_evaluation(cards):
    result, evaluated = _run([TOO_SMALL] * 3, cards)
    assert result.generation_attempts == 3
    assert result.decklist is None
    assert result.evaluation is None
    assert any("50 cards" in e for e in result.errors)
    assert evaluated == []
