import re
from pathlib import Path
from typing import Annotated

import typer

from op_tcg_evaluator.config import get_settings
from op_tcg_evaluator.db import init_db
from op_tcg_evaluator.db.seed import seed_db
from op_tcg_evaluator.graph import (
    EvaluatorState,
    GeneratorState,
    PipelineState,
    build_generator_graph,
    build_graph,
    build_pipeline_graph,
)
from op_tcg_evaluator.models import CARD_ID_PATTERN

app = typer.Typer(help="Evaluate One Piece TCG decklists.", no_args_is_help=True)


@app.command("init-db")
def init_db_command() -> None:
    """Create the SQLite database and tables."""
    db_path = get_settings().db_path
    init_db(db_path)
    typer.echo(f"Initialized database at {db_path}")


@app.command()
def seed() -> None:
    """Seed the database with card data."""
    seed_db(get_settings().db_path)


@app.command()
def evaluate(
    decklist_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Evaluate a decklist file (leader id on line 1, then '<qty>x<card id>' lines)."""
    graph = build_graph()
    result = EvaluatorState.model_validate(
        graph.invoke(EvaluatorState(raw_decklist=decklist_file.read_text(encoding="utf-8")))
    )
    if result.errors:
        for error in result.errors:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.evaluation.model_dump_json(indent=2))


@app.command()
def generate(
    leader_id: Annotated[str, typer.Argument(help="Leader card ID, e.g. OP01-001.")],
) -> None:
    """Have Claude build a 50-card deck for a leader and print it as a decklist file."""
    _require_card_id(leader_id)
    graph = build_generator_graph()
    result = GeneratorState.model_validate(graph.invoke(GeneratorState(leader_id=leader_id)))
    if result.decklist is None:
        typer.echo(f"error: no valid deck after {result.attempts} attempts", err=True)
        for error in result.errors:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.decklist.to_text(), nl=False)


@app.command()
def build(
    leader_id: Annotated[str, typer.Argument(help="Leader card ID, e.g. OP01-001.")],
) -> None:
    """Generate a deck for a leader, evaluate it, and print both as one JSON object."""
    _require_card_id(leader_id)
    graph = build_pipeline_graph()
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


def _require_card_id(card_id: str) -> None:
    # Checked before any graph runs so a typo fails immediately instead of costing an API call.
    if not re.fullmatch(CARD_ID_PATTERN, card_id):
        typer.echo(f"error: {card_id!r} is not a card ID like OP01-001", err=True)
        raise typer.Exit(code=1)
