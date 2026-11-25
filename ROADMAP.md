# Roadmap

**Goal:** make generated decks as strong as possible by testing them in a deterministic game engine against real meta decks, and using those results to refine the decklist.

The principle carries over from today's code: Claude proposes, code decides. Claude picks cards and suggests changes. A seeded, reproducible simulation decides whether a change actually made the deck better.

## Done

- [x] Local card database imported from optcgapi, with an import report and verified subtype overrides
- [x] Generation with the leader's legal card pool, including full effect text
- [x] Deterministic legality checks: 50 cards, at most 4 copies, real cards, no Leaders in the main deck, leader color
- [x] Evaluation with full card details for every deck card
- [x] Zero-trust handling of Claude's output, third-party card data, and decklist files
- [x] HTML deck page with the score, deck stats, analysis, and card images

## Phase 0: Close known gaps

Small items found while building the current version. Most are worth doing before the engine, since the engine will trust this data.

- [ ] **Format legality.** Add the official ban and restricted list and block rotation (the official card list shows a block icon per card). Today a banned or rotated-out card passes every check. Needs a data source we can verify.
- [ ] **DON!! deck.** Model the 10-card DON!! deck. Decklists don't need it, but the engine does.
- [ ] **Errata text.** `card_text` comes from each card's original printing, so about 450 cards may show pre-errata wording. Prefer errata'd text where a later printing marks it.
- [ ] **Remaining subtypes.** 95 subtypes are inferred and not all checked against the official list. Verify them, since type-based effects ("your {Straw Hat Crew} Characters") will depend on them.
- [ ] **Promo cards.** optcgapi's promo endpoint returned 404. Recheck it, or find another source for promos that never appeared in a set.
- [ ] **Keyword spelling.** Effect text mixes `[Activate:Main]` and `[Activate: Main]`. Normalize keywords at import so the engine's parser sees one form.
- [ ] **Prompt cost.** The generator's card pool is about 28k tokens (one color) to 57k (two colors) per attempt. Try prompt caching for the pool, since it's identical across retries.

## Phase 1: Meta deck gauntlet

The decks every generated deck is tested against.

- [ ] Research sources of recent tournament decklists, and check each one's terms for automated use.
- [ ] Store meta decks in the DB with a name, leader, list, date, source, and event placement.
- [ ] Validate every imported meta deck through the same legality checks as generated decks. Third-party decklists are untrusted input like any other.
- [ ] Choose a gauntlet: for example, the top N leaders by recent results, weighted by how often they appear.
- [ ] Refresh command (like `fetch-cards`) so the gauntlet can track the current meta.

## Phase 2: Deterministic game engine, core rules

A rules engine that plays full games between two decklists. Same decks plus the same seed must always give the same result.

- [ ] Game state: life cards, hand, deck, trash, Character area (5-card limit), Stage, DON!! deck, cost area, and attached DON!!.
- [ ] Turn structure: refresh, draw (no draw for the first player on turn 1), DON!! phase, main phase, and battle.
- [ ] Battle: attacking with rested cards, power comparison, attached DON!! (+1000 each on your turn), block step, counter step (counter values from hand), damage, and life cards going to hand.
- [ ] Win conditions: leader damaged at 0 life, or a player can't draw.
- [ ] A seeded random-number generator as the only source of randomness. No wall-clock time, no unseeded shuffles.
- [ ] Rules tests written from the official comprehensive rules, one test per rule implemented.
- [ ] Game log output, so any simulated game can be replayed and read step by step.

## Phase 3: Card effects

The hard part: 2,366 of 2,632 non-Leader cards have effect text. Build coverage in layers and always report how much of a deck the engine actually understands.

- [ ] **Layer 1, static keywords:** [Blocker], [Rush], [Double Attack], [Banish], and [Unblockable]. These come straight from the text.
- [ ] **Layer 2, common effect patterns:** draw N, K.O. up to 1 with cost N or less, give power, rest a Character, add DON!!, and [Trigger] effects. Parse the common phrasings and use them for timing like [On Play], [When Attacking], and [Counter].
- [ ] **Layer 3, scripted cards:** hand-written effects for the cards that matter most, prioritized by how often they appear in the meta gauntlet and in generated decks.
- [ ] **Coverage report:** for each deck, the share of cards whose effects are fully, partly, or not implemented. Results for decks with low coverage are flagged as unreliable.
- [ ] Leader effects, starting with the leaders in the gauntlet.

## Phase 4: Player AI and simulation harness

- [ ] A baseline AI that makes reasonable plays (curve out, attack sensibly, block and counter to protect life) and is fully deterministic.
- [ ] Mirror both sides: each matchup is played with each deck going first, since first-player advantage is significant.
- [ ] Run many seeded games per matchup and report win rate with a confidence interval. For example, 1,000 games gives roughly ±3 percentage points at 95% confidence.
- [ ] Per-matchup stats beyond win rate: average game length, damage taken by turn, and cards that were never played.
- [ ] Parallel runs and a result cache keyed by (deck, opponent, seed, engine version), so unchanged matchups aren't re-simulated.

## Phase 5: Refinement loop

Use simulation results to improve the deck, with Claude proposing and the engine judging.

- [ ] Give Claude the deck, its matchup table, and per-card stats. Ask for a small number of specific swaps, chosen only from the legal card pool.
- [ ] Validate every proposed swap with the existing legality checks before any simulation runs.
- [ ] Keep a swap only if the gauntlet win rate improves by more than the confidence interval. Otherwise discard it and record why.
- [ ] Stop after a fixed budget of iterations or simulated games, or when several rounds in a row bring no improvement.
- [ ] Record every iteration (deck, swaps, win rates, seeds) so any refined deck can be reproduced and traced back.
- [ ] Compare against a non-LLM baseline (random or greedy swaps) to check that Claude's suggestions beat blind search.

## Phase 6: Reporting

- [ ] Deck page: matchup table against the gauntlet, the refinement history, and engine coverage.
- [ ] Separate Claude's opinions from simulated results on the page, so it's always clear which is which.
- [ ] `refine` CLI command: generate a deck (or load one), refine it, and write the page.

## Decisions to make before building

These shape the architecture, so they should be decided together up front.

1. **Engine location:** a module inside this package, or a separate package that the evaluator calls.
2. **Effect representation:** Python functions per card, or a small effect language that card text is parsed into.
3. **Rules fidelity:** how close to the full comprehensive rules the first version must be before its results are trusted.
4. **Meta deck source:** which source, and how often to refresh.
5. **AI strength:** how much effort goes into the player AI. A weak AI makes win rates misleading, but a strong one is a project of its own.
6. **Compute budget:** games per matchup, and how long a full refinement run may take.

## Risks

- **Effect coverage:** a simulation that ignores most effects will reward big stats and penalize decks that win through effects. The coverage report exists to keep this visible.
- **AI bias:** win rates measure the deck and the AI together. Both sides use the same AI, but some decks need careful play that a simple AI won't make.
- **Meta drift:** a gauntlet goes stale after each set release and ban list update. Results should always show the gauntlet's date.
- **Overfitting:** refining against a fixed gauntlet can produce a deck that beats those exact lists and little else. Hold some meta decks out of refinement and test the final deck against them.
