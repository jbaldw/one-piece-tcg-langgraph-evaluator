from op_tcg_evaluator.graph import GeneratorState, build_generator_graph
from op_tcg_evaluator.graph.nodes import build_generation_prompt
from op_tcg_evaluator.models import DeckDraft

LEADER = "OP01-001"


def _draft(*quantities: int, leader: str = LEADER) -> DeckDraft:
    cards = [{"card_id": f"OP01-{i:03d}", "quantity": q} for i, q in enumerate(quantities, 2)]
    return DeckDraft(leader_id=leader, cards=cards)


VALID = _draft(*[4] * 12, 2)
TOO_SMALL = _draft(4, 4)


def _fake_generator(replies: list[DeckDraft | None]):
    """Stand-in for the Claude call: returns the next reply each time it runs.

    None simulates a reply that didn't match the schema.
    """
    remaining = list(replies)

    def node(state: GeneratorState) -> dict:
        reply = remaining.pop(0)
        update = {"attempts": state.attempts + 1}
        if reply is None:
            return update | {"draft": None, "errors": ["response did not match the schema"]}
        return update | {"draft": reply, "errors": []}

    return node


def _run(replies: list[DeckDraft | None]) -> GeneratorState:
    graph = build_generator_graph(generate_node=_fake_generator(replies))
    return GeneratorState.model_validate(graph.invoke(GeneratorState(leader_id=LEADER)))


def test_valid_on_first_try():
    result = _run([VALID])
    assert result.attempts == 1
    assert result.decklist is not None
    assert result.errors == []


def test_valid_on_third_try():
    result = _run([TOO_SMALL, None, VALID])
    assert result.attempts == 3
    assert result.decklist is not None


def test_gives_up_after_three_tries():
    # A 4th reply is queued to prove the graph never asks for it.
    result = _run([TOO_SMALL, TOO_SMALL, TOO_SMALL, VALID])
    assert result.attempts == 3
    assert result.decklist is None
    assert any("50 cards" in e for e in result.errors)


def test_wrong_leader_is_rejected():
    result = _run([_draft(*[4] * 12, 2, leader="OP02-001")] * 3)
    assert result.decklist is None
    assert any("leader_id must be OP01-001" in e for e in result.errors)


def test_first_prompt_has_no_feedback():
    prompt = build_generation_prompt(GeneratorState(leader_id=LEADER))
    assert LEADER in prompt
    assert "previous attempt" not in prompt.lower()


def test_retry_prompt_includes_previous_attempt_and_errors():
    state = GeneratorState(
        leader_id=LEADER,
        attempts=1,
        draft=TOO_SMALL,
        errors=["main deck must have 50 cards, got 8"],
    )
    prompt = build_generation_prompt(state)
    assert TOO_SMALL.to_text() in prompt
    assert "main deck must have 50 cards, got 8" in prompt
