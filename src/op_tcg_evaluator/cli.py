import re
from pathlib import Path
from typing import Annotated

import typer

from op_tcg_evaluator.config import get_settings
from op_tcg_evaluator.db import init_db
from op_tcg_evaluator.db.optcgapi import cache_dir, fetch_all
from op_tcg_evaluator.db.seed import seed_db
from op_tcg_evaluator.deck_view import open_in_browser, write_deck_page
from op_tcg_evaluator.graph import (
    EvaluatorState,
    GeneratorState,
    PipelineState,
    build_generator_graph,
    build_graph,
    build_pipeline_graph,
)
from op_tcg_evaluator.graph.nodes import parse_decklist
from op_tcg_evaluator.models import CARD_ID_PATTERN, EvaluationResult
from op_tcg_evaluator.rules import CardLookup, check_deck_rules, leader_problem

app = typer.Typer(help="Evaluate One Piece TCG decklists.", no_args_is_help=True)

ShowOption = Annotated[
    bool, typer.Option("--show", help="Also write an HTML page of the deck's card images.")
]


@app.command("init-db")
def init_db_command() -> None:
    """Create the SQLite database and tables."""
    db_path = get_settings().db_path
    init_db(db_path)
    typer.echo(f"Initialized database at {db_path}")


@app.command("fetch-cards")
def fetch_cards() -> None:
    """Download the official card list from optcgapi.com into the data directory."""
    dest = cache_dir(get_settings().db_path)
    counts = fetch_all(dest)
    summary = ", ".join(f"{n} {source}" for source, n in counts.items())
    typer.echo(f"Saved {summary} printings to {dest}")


@app.command()
def seed() -> None:
    """Load the cached card list (from fetch-cards) into the database."""
    seed_db(get_settings().db_path)


@app.command()
def evaluate(
    decklist_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Evaluate a decklist file (leader id on line 1, then '<qty>x<card id>' lines)."""
    graph = build_graph()
    result = EvaluatorState.model_validate(
        graph.invoke(EvaluatorState(raw_decklist=_read_decklist(decklist_file)))
    )
    if result.errors:
        for error in result.errors:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.evaluation.model_dump_json(indent=2))


@app.command()
def generate(
    leader_id: Annotated[str, typer.Argument(help="Leader card ID, e.g. OP01-001.")],
    show: ShowOption = False,
) -> None:
    """Have Claude build a 50-card deck for a leader and print it as a decklist file."""
    cards = _require_leader(leader_id)
    graph = build_generator_graph(cards=cards)
    result = GeneratorState.model_validate(graph.invoke(GeneratorState(leader_id=leader_id)))
    if result.decklist is None:
        typer.echo(f"error: no valid deck after {result.attempts} attempts", err=True)
        for error in result.errors:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.decklist.to_text(), nl=False)
    if show:
        _show_deck(result.decklist.leader_id, _entries(result.decklist), cards)


@app.command()
def build(
    leader_id: Annotated[str, typer.Argument(help="Leader card ID, e.g. OP01-001.")],
    show: ShowOption = False,
) -> None:
    """Generate a deck for a leader, evaluate it, and print both as one JSON object."""
    cards = _require_leader(leader_id)
    graph = build_pipeline_graph(cards=cards)
    result = PipelineState.model_validate(graph.invoke(PipelineState(leader_id=leader_id)))
    if result.evaluation is None:
        if result.decklist is None:
            typer.echo(
                f"error: no valid deck after {result.generation_attempts} attempts", err=True
            )
        for error in result.errors:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.model_dump_json(include={"decklist", "evaluation"}, indent=2))
    if show:
        _show_deck(result.decklist.leader_id, _entries(result.decklist), cards, result.evaluation)


@app.command("show")
def show_command(
    decklist_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Write an HTML page of a decklist's card images and open it in your browser."""
    parsed = parse_decklist(EvaluatorState(raw_decklist=_read_decklist(decklist_file)))
    if parsed.get("errors"):
        for error in parsed["errors"]:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1)
    leader_id, entries = parsed["leader_id"], parsed["entries"]

    cards = CardLookup(get_settings().db_path)
    known = cards.get_many([leader_id, *(cid for cid, _ in entries)])
    problem = leader_problem(leader_id, known)
    blocking = [problem] if problem else []
    blocking += [f"{cid} is not in the card database" for cid, _ in entries if cid not in known]
    if blocking:
        for error in blocking:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1)
    # A deck that breaks a rule (e.g. an off-color card) is still worth looking at.
    for problem in check_deck_rules(leader_id, [cid for cid, _ in entries], cards):
        typer.echo(f"warning: {problem}", err=True)
    _show_deck(leader_id, entries, cards)


def _require_leader(card_id: str) -> CardLookup:
    # Checked before any graph runs so a typo or non-leader fails immediately instead of
    # costing an API call.
    if not re.fullmatch(CARD_ID_PATTERN, card_id):
        typer.echo(f"error: {card_id!r} is not a card ID like OP01-001", err=True)
        raise typer.Exit(code=1)
    cards = CardLookup(get_settings().db_path)
    problem = leader_problem(card_id, cards.get_many([card_id]))
    if problem:
        typer.echo(f"error: {problem}", err=True)
        raise typer.Exit(code=1)
    return cards


def _entries(decklist) -> list[tuple[str, int]]:
    return [(e.card_id, e.quantity) for e in decklist.cards]


def _show_deck(
    leader_id: str,
    entries: list[tuple[str, int]],
    cards: CardLookup,
    evaluation: EvaluationResult | None = None,
) -> None:
    # Status goes to stderr so generate's decklist and build's JSON on stdout stay clean.
    decks_dir = get_settings().db_path.parent / "decks"
    path = write_deck_page(leader_id, entries, cards, decks_dir, evaluation)
    try:
        shown = path.resolve().relative_to(Path.cwd())
    except ValueError:
        shown = path
    if open_in_browser(path):
        typer.echo(f"Opened deck page {shown}", err=True)
    else:
        typer.echo(f"Deck page written to {shown}; open it in your browser.", err=True)


def _read_decklist(path: Path) -> str:
    # utf-8-sig drops the byte-order mark PowerShell's `>` writes, which would otherwise
    # become part of the leader ID.
    return path.read_text(encoding="utf-8-sig")
