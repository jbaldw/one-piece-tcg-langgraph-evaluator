# one-piece-tcg-langgraph-evaluator
This project aims to create a full end-to-end agentic evaluator of One Piece TCG decklists to aid in the process of optimizing tournament-ready decks.

## Running

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

With Docker (the SQLite database persists in `./data`):

```bash
docker compose build
docker compose run --rm evaluator init-db
docker compose run --rm evaluator seed
docker compose run --rm evaluator evaluate /app/data/my_deck.txt
docker compose run --rm -T evaluator generate OP01-001 > data/generated_deck.txt
```

To generate and evaluate in one run, use `build`, which prints `{"decklist": ..., "evaluation": ...}` as JSON:

```bash
docker compose run --rm evaluator build OP01-001
```

`generate` asks Claude for a 50-card deck for the given leader, retrying up to 3 times with the validation errors fed back, and prints it in the decklist format `evaluate` reads.

Locally with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run op-eval --help
uv run pytest
```

Decklist files list the leader id on the first line, then one `<qty>x<card id>` per line (e.g. `4xOP01-016`).
