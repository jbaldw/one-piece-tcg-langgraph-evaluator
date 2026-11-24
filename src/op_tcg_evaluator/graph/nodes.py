import re

from pydantic import ValidationError

from op_tcg_evaluator.graph.state import EvaluatorState, GeneratorState
from op_tcg_evaluator.llm import get_chat_model
from op_tcg_evaluator.models import (
    MAIN_DECK_SIZE,
    MAX_COPIES,
    DeckDraft,
    DeckEntry,
    Decklist,
    EvaluationResult,
)

# Decklist text format: first non-empty line is the leader id, then "<qty>x<card id>" lines.
_ENTRY_RE = re.compile(r"^(\d+)\s*x\s*(\S+)$", re.IGNORECASE)


def format_validation_errors(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(map(str, err['loc']))}: {err['msg']}" if err["loc"] else err["msg"]
        for err in exc.errors()
    ]


def parse_decklist(state: EvaluatorState) -> dict:
    lines = [line.strip() for line in state.raw_decklist.splitlines() if line.strip()]
    if not lines:
        return {"errors": ["decklist is empty"]}

    leader_id, *entry_lines = lines
    entries: list[tuple[str, int]] = []
    errors: list[str] = []
    for line in entry_lines:
        match = _ENTRY_RE.match(line)
        if not match:
            errors.append(f"could not parse line: {line!r}")
            continue
        entries.append((match[2], int(match[1])))

    if errors:
        return {"errors": errors}
    return {"leader_id": leader_id, "entries": entries}


def validate_deck(state: EvaluatorState) -> dict:
    try:
        decklist = Decklist(
            leader_id=state.leader_id,
            cards=[DeckEntry(card_id=cid, quantity=qty) for cid, qty in state.entries],
        )
    except ValidationError as exc:
        return {"errors": format_validation_errors(exc)}
    return {"decklist": decklist}


def evaluate(state: EvaluatorState) -> dict:
    model = get_chat_model().with_structured_output(EvaluationResult, method="json_schema")
    prompt = (
        "You are an expert One Piece TCG deck builder. Evaluate this decklist for "
        "competitive tournament play.\n\n"
        f"{state.decklist.model_dump_json(indent=2)}"
    )
    return {"evaluation": model.invoke(prompt)}


def build_generation_prompt(state: GeneratorState) -> str:
    prompt = (
        "You are an expert One Piece TCG deck builder. Build a competitive tournament deck "
        f"for the leader {state.leader_id}.\n\n"
        "Rules:\n"
        f"- leader_id must be exactly {state.leader_id}.\n"
        f"- The cards must add up to exactly {MAIN_DECK_SIZE} (sum of all quantities).\n"
        f"- Each card_id appears at most once in the list, with a quantity from 1 to "
        f"{MAX_COPIES}.\n"
        "- Card IDs use the official format, e.g. OP01-016.\n"
        "- Do not put the leader card in the cards list.\n"
    )
    if state.errors:
        prompt += "\nYour previous attempt was invalid.\n"
        if state.draft is not None:
            prompt += f"Previous attempt:\n{state.draft.to_text()}"
        prompt += "Fix these errors:\n" + "\n".join(f"- {e}" for e in state.errors) + "\n"
    return prompt


def generate_deck(state: GeneratorState) -> dict:
    model = get_chat_model().with_structured_output(
        DeckDraft, method="json_schema", include_raw=True
    )
    # include_raw=True returns schema/validation failures as data instead of raising,
    # so they can be fed back to Claude on the next attempt.
    result = model.invoke(build_generation_prompt(state))
    update = {"attempts": state.attempts + 1}
    if result["parsing_error"] is not None:
        return update | {
            "draft": None,
            "errors": [f"response did not match the schema: {result['parsing_error']}"],
        }
    return update | {"draft": result["parsed"], "errors": []}


def check_deck(state: GeneratorState) -> dict:
    if state.draft is None:
        return {}

    errors: list[str] = []
    if state.draft.leader_id != state.leader_id:
        errors.append(f"leader_id must be {state.leader_id}, got {state.draft.leader_id}")
    try:
        decklist = Decklist.model_validate(state.draft.model_dump())
    except ValidationError as exc:
        errors.extend(format_validation_errors(exc))

    if errors:
        return {"errors": errors}
    return {"decklist": decklist}
