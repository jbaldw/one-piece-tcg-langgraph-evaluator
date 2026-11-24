from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

# Placeholder limits; the full deck-legality rules will replace these.
MAIN_DECK_SIZE = 50
MAX_COPIES = 4
CARD_ID_PATTERN = r"^[A-Z0-9]+-\d{3}$"


class CardCategory(StrEnum):
    LEADER = "Leader"
    CHARACTER = "Character"
    EVENT = "Event"
    STAGE = "Stage"


class Card(BaseModel):
    id: str = Field(pattern=CARD_ID_PATTERN, examples=["OP01-001"])
    name: str
    category: CardCategory
    color: str
    cost: int | None = Field(default=None, ge=0)
    power: int | None = Field(default=None, ge=0)
    counter: int | None = Field(default=None, ge=0)
    set_code: str | None = None


class DeckEntry(BaseModel):
    card_id: str = Field(pattern=CARD_ID_PATTERN)
    quantity: int = Field(ge=1, le=MAX_COPIES)


class DeckDraft(BaseModel):
    """A deck with per-card rules only. Also the schema Claude fills when generating a deck.

    The whole-deck rules live on Decklist so that a wrong card count comes back as a
    validation error we can send to Claude, instead of being part of Claude's schema.
    """

    leader_id: str = Field(pattern=CARD_ID_PATTERN)
    cards: list[DeckEntry]

    def to_text(self) -> str:
        """Render in the decklist text format that `evaluate` reads."""
        lines = [self.leader_id] + [f"{e.quantity}x{e.card_id}" for e in self.cards]
        return "\n".join(lines) + "\n"


class Decklist(DeckDraft):
    @model_validator(mode="after")
    def check_composition(self) -> "Decklist":
        ids = [entry.card_id for entry in self.cards]
        if len(ids) != len(set(ids)):
            raise ValueError("each card id may appear only once; combine quantities")
        total = sum(entry.quantity for entry in self.cards)
        if total != MAIN_DECK_SIZE:
            raise ValueError(f"main deck must have {MAIN_DECK_SIZE} cards, got {total}")
        return self


class EvaluationResult(BaseModel):
    score: int = Field(ge=0, le=100, description="Overall competitive rating, 0-100.")
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
