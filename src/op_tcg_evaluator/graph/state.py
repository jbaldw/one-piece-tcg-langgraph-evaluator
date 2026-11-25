from pydantic import BaseModel, Field

from op_tcg_evaluator.models import DeckDraft, Decklist, EvaluationResult


class EvaluatorState(BaseModel):
    raw_decklist: str
    # Unvalidated parse output; LangGraph re-validates state, so a Decklist can't hold it.
    leader_id: str | None = None
    entries: list[tuple[str, int]] = Field(default_factory=list)
    decklist: Decklist | None = None
    errors: list[str] = Field(default_factory=list)
    evaluation: EvaluationResult | None = None


class GeneratorState(BaseModel):
    leader_id: str
    attempts: int = 0
    # Latest reply from Claude; None when the reply didn't match the DeckDraft schema.
    draft: DeckDraft | None = None
    errors: list[str] = Field(default_factory=list)
    decklist: Decklist | None = None


class PipelineState(BaseModel):
    leader_id: str
    generation_attempts: int = 0
    decklist: Decklist | None = None
    errors: list[str] = Field(default_factory=list)
    evaluation: EvaluationResult | None = None
