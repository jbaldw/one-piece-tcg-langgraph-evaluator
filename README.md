# One Piece TCG Deck Evaluator

Give it a leader, and it builds a legal 50-card deck with Claude, scores it for tournament play, and shows you the cards.

## Quick start

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) and an [Anthropic API key](https://console.anthropic.com/). Commands are for PowerShell, run from this folder.

**1. Add your API key.** Copy the example settings, then open `.env` and paste your key after `ANTHROPIC_API_KEY=`.

```powershell
Copy-Item .env.example .env
```

**2. Build the app.**

```powershell
docker compose build
```

**3. Download the card list and load it.** This is a one-time step (about 3 MB from optcgapi.com).

```powershell
docker compose run --rm evaluator fetch-cards
```

```powershell
docker compose run --rm evaluator seed
```

**4. Build a deck.** This generates a deck for Roronoa Zoro (`OP01-001`), evaluates it, and writes a page of card images.

```powershell
docker compose run --rm evaluator build OP01-001 --show
```

Open the page it names (for example `data/decks/OP01-001-20261125-203319.html`) in your browser to see the cards.

## Everyday commands

The `data` folder in this project is `/app/data` inside the container, so files you save there are visible to the app.

| To do this | Run this |
|---|---|
| Generate a deck and evaluate it | `docker compose run --rm evaluator build OP01-001` |
| Generate a deck and save it to a file | `docker compose run --rm -T evaluator generate OP01-001 > data\my_deck.txt` |
| Evaluate a deck you wrote | `docker compose run --rm evaluator evaluate /app/data/my_deck.txt` |
| See a deck's card images | `docker compose run --rm evaluator show /app/data/my_deck.txt` |
| Get new sets after a release | `docker compose run --rm evaluator fetch-cards`, then `seed` |
| See every command and option | `docker compose run --rm evaluator --help` |

Add `--show` to `generate` or `build` to also write the card-image page. Use `-T` whenever you save output with `>`, so the file gets plain text.

### Decklist format

The leader ID goes on the first line, then one `<quantity>x<card ID>` per line:

```
OP01-001
4xOP01-016
4xOP01-013
2xOP01-029
```

The main deck must total exactly 50 cards, with at most 4 copies of each card ID.

## How it works

1. **Card data.** `fetch-cards` downloads every card from [optcgapi.com](https://optcgapi.com/documentation), and `seed` cleans it into a local SQLite database: one row per card, with its colors and types in lookup tables.
2. **Generate.** Claude gets the leader's stats and the list of every card that shares the leader's color, and picks a deck from that list.
3. **Check.** Plain code checks the deck against the database: 50 cards, at most 4 copies, every card real, no Leaders in the main deck, and every card in the leader's color. If anything fails, the exact errors go back to Claude, which gets up to 3 attempts.
4. **Evaluate.** Claude scores the legal deck and lists strengths, weaknesses, and suggestions.

## Why it's built this way

### Zero-trust by default

Nothing that crosses into the app is trusted until code has checked it. There are three such boundaries: Claude's replies, the third-party card data, and the decklist files you pass in.

**Why:** a language model can be wrong, and it can be manipulated. Prompt injection means text that looks like data ("ignore your rules and...") gets treated as instructions. If unchecked text from one step flows into the next prompt, database query, or web page, one bad reply or one tampered card record can steer everything after it. Checking at every boundary puts the guarantees in code, where they hold even when the model misbehaves.

What that looks like in practice:

- **Claude's replies** must match a strict schema (card IDs like `OP01-016`, quantities 1 to 4) before anything uses them. If a reply fails, the retry prompt describes what was wrong without quoting the reply, so a malformed reply can't plant instructions in the next attempt.
- **Card data from optcgapi** is placed in the prompt inside `<leader>` and `<card_pool>` tags, with angle brackets escaped so card text can't close a tag. Claude is told that tagged text is data, never instructions. Every `seed` also scans card text for anything that looks aimed at an AI and reports it.
- **The card-image page** escapes all card text and only loads images from optcgapi's own image folder.
- **Database queries** always pass values as parameters, never pasted into the SQL.

### Code decides legality, Claude decides strategy

Whether a deck is legal is a fact that code can check exactly. Claude handles what code can't: picking a strong, coherent deck and judging it.

**Why:** models misremember card IDs and colors, and a rule a model "usually" follows is not a rule. Deterministic checks are free, instant, and always right, and their error messages give Claude precise feedback to fix its next attempt.

### A local card database

The card list is downloaded once and kept in `data/`. Re-seeding, generating, and evaluating never call optcgapi again.

**Why:** optcgapi is a free community service that asks users to keep their call volume low. A local copy is also faster, works offline, and gives repeatable results.

### Bad source data is fixed in the open

The API has real errors: printings of the same card that disagree, columns shifted by one, and multi-word types run together with spaces. `seed` resolves each one by a fixed rule and lists every decision in `data/optcgapi/import_report.csv`. Types that can't be split automatically are corrected in [type_overrides.json](src/op_tcg_evaluator/db/type_overrides.json), and each entry was checked against Bandai's official card list.

**Why:** silently "fixing" data hides mistakes. A report you can read means a wrong value can be traced and corrected.

### Fail fast, before spending money

`generate` and `build` check that the leader exists and is a Leader before calling Claude.

**Why:** a typo should cost nothing. API calls cost money and time, so cheap checks run first.

## Troubleshooting

- **`no card database at ...`**: run `fetch-cards`, then `seed` (step 3 of the quick start).
- **`... is not in the card database`**: check the card ID for typos. If the card is from a new set, run `fetch-cards` and `seed` again.
- **`WARNING: ... card fields look like they contain text aimed at an LLM`**: the downloaded card data contains suspicious text. Look at the `SUSPICIOUS_TEXT` rows in `data/optcgapi/import_report.csv` before generating.
- **The card-image page didn't open by itself**: that's expected from Docker, since the container can't open your browser. Open the file it names in the `data/decks` folder.

## Development

Run the app and tests without Docker using [uv](https://docs.astral.sh/uv/). The tests use a small built-in card database and never call Claude, so they need no API key.

```powershell
uv sync
```

```powershell
uv run pytest
```

```powershell
uv run op-eval --help
```
