"""Render a decklist, and optionally Claude's evaluation of it, as a standalone HTML page."""

import webbrowser
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

from op_tcg_evaluator.models import Card, CardCategory, EvaluationResult
from op_tcg_evaluator.rules import CardLookup

# Image URLs come from third-party data, so only optcgapi's own image path is linked.
ALLOWED_IMAGE_PREFIX = "https://optcgapi.com/media/"

_SECTIONS = [CardCategory.CHARACTER, CardCategory.EVENT, CardCategory.STAGE]
_COLOR_HEX = {
    "Red": "#d9363e",
    "Green": "#2e9e5b",
    "Blue": "#2f7fd8",
    "Purple": "#8a4fd0",
    "Black": "#5b5f6b",
    "Yellow": "#e3b520",
}
_MAX_CURVE_COST = 10

_STYLE = """
:root { --bg: #0f1116; --panel: #181b22; --line: #262a33; --text: #e9eaee;
        --muted: #9aa0ab; --good: #2e9e5b; --bad: #d9363e; --idea: #2f7fd8; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
       font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1200px; margin: 0 auto; padding: 32px 24px 64px; }
h2 { font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted);
     margin: 40px 0 14px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; }

.hero { display: grid; grid-template-columns: 240px 1fr auto; gap: 28px; padding: 24px;
        align-items: start; }
.hero img, .hero .missing { width: 240px; aspect-ratio: 600 / 838; border-radius: 12px;
        object-fit: cover; box-shadow: 0 12px 32px rgba(0,0,0,.5); }
.hero h1 { margin: 0 0 4px; font-size: 30px; line-height: 1.2; }
.hero .id { color: var(--muted); font-size: 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }
.chip { padding: 3px 12px; border-radius: 999px; font-size: 13px; font-weight: 600;
        background: var(--line); }
.effect { background: var(--bg); border: 1px solid var(--line); border-radius: 10px;
          padding: 12px 14px; color: #cfd2d9; font-size: 14px; }
.score { --pct: 0; width: 132px; height: 132px; border-radius: 50%; display: grid;
         place-items: center; background: conic-gradient(var(--ring) calc(var(--pct) * 1%),
         var(--line) 0); }
.score div { width: 104px; height: 104px; border-radius: 50%; background: var(--panel);
             display: grid; place-items: center; text-align: center; }
.score b { font-size: 34px; line-height: 1; }
.score span { font-size: 12px; color: var(--muted); }

.stats { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 16px; }
.stats .panel { padding: 18px 20px; }
.stats h3 { margin: 0 0 12px; font-size: 14px; color: var(--muted); font-weight: 600; }
.curve { display: flex; align-items: flex-end; gap: 6px; height: 120px; }
.bar { flex: 1; display: flex; flex-direction: column; align-items: center;
       justify-content: flex-end; height: 100%; font-size: 12px; color: var(--muted); }
.bar i { display: block; width: 100%; border-radius: 4px 4px 0 0; background: var(--accent);
         min-height: 2px; }
.bar em { font-style: normal; color: var(--text); margin-bottom: 2px; }
.kv { display: flex; justify-content: space-between; padding: 6px 0;
      border-bottom: 1px solid var(--line); }
.kv:last-child { border-bottom: 0; }
.kv b { font-variant-numeric: tabular-nums; }

.analysis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.analysis .panel { padding: 18px 20px; border-top: 3px solid var(--tone); }
.analysis h3 { margin: 0 0 10px; font-size: 16px; color: var(--tone); }
.analysis ul { margin: 0; padding-left: 18px; }
.analysis li { margin: 0 0 8px; color: #d6d8de; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 18px; }
.card { position: relative; margin: 0; transition: transform .15s ease; }
.card:hover { transform: scale(1.06); z-index: 1; }
.card img, .card .missing { width: 100%; aspect-ratio: 600 / 838; border-radius: 10px;
        display: block; object-fit: cover; box-shadow: 0 6px 18px rgba(0,0,0,.45); }
.missing { display: flex !important; align-items: center; justify-content: center;
           background: var(--line); color: var(--muted); }
.qty { position: absolute; top: 8px; right: 8px; background: rgba(15,17,22,.88);
       border: 1px solid var(--line); color: #fff; font-weight: 700; border-radius: 999px;
       padding: 2px 10px; font-size: 14px; }
figcaption { margin-top: 8px; font-size: 13px; line-height: 1.35; }
figcaption .id { color: var(--muted); }
footer { margin-top: 48px; color: var(--muted); font-size: 12px; }

@media (max-width: 900px) {
  .hero { grid-template-columns: 1fr; }
  .stats, .analysis { grid-template-columns: 1fr; }
}
"""


def _image_tag(card: Card, url: str | None) -> str:
    if url and url.startswith(ALLOWED_IMAGE_PREFIX):
        return f'<img src="{escape(url)}" alt="{escape(card.name)}" loading="lazy">'
    return '<div class="missing">No image</div>'


def _figure(card: Card, url: str | None, quantity: int) -> str:
    cost = f" &middot; cost {card.cost}" if card.cost is not None else ""
    return (
        f'<figure class="card">{_image_tag(card, url)}<span class="qty">{quantity}x</span>'
        f'<figcaption><span class="id">{escape(card.id)}</span><br>'
        f"{escape(card.name)}{cost}</figcaption></figure>"
    )


def _hero(leader: Card, url: str | None, evaluation: EvaluationResult | None) -> str:
    chips = "".join(
        f'<span class="chip" style="background:{_COLOR_HEX.get(c, "#262a33")}">{escape(c)}</span>'
        for c in leader.colors
    )
    chips += f'<span class="chip">{leader.power} power</span>' if leader.power else ""
    chips += f'<span class="chip">{leader.life} life</span>' if leader.life else ""
    chips += "".join(f'<span class="chip">{escape(t)}</span>' for t in leader.types)
    effect = f'<div class="effect">{escape(leader.card_text)}</div>' if leader.card_text else ""
    score = ""
    if evaluation is not None:
        ring = (
            "#2e9e5b"
            if evaluation.score >= 70
            else "#e3b520"
            if evaluation.score >= 40
            else "#d9363e"
        )
        score = (
            f'<div class="score" style="--pct:{evaluation.score};--ring:{ring}">'
            f"<div><span><b>{evaluation.score}</b><br>score / 100</span></div></div>"
        )
    return (
        f'<section class="hero panel">{_image_tag(leader, url)}'
        f'<div><div class="id">{escape(leader.id)} &middot; Leader</div>'
        f'<h1>{escape(leader.name)}</h1><div class="chips">{chips}</div>{effect}</div>'
        f"{score}</section>"
    )


def _stats(entries: list[tuple[str, int]], cards: dict[str, Card], accent: str) -> str:
    curve: Counter[int] = Counter()
    counters: Counter[int] = Counter()
    categories: Counter[str] = Counter()
    for cid, qty in entries:
        card = cards[cid]
        if card.cost is not None:
            curve[min(card.cost, _MAX_CURVE_COST)] += qty
        counters[card.counter or 0] += qty
        categories[card.category] += qty
    tallest = max(curve.values(), default=1)
    bars = "".join(
        f'<div class="bar"><em>{curve[c] or ""}</em>'
        f'<i style="height:{curve[c] / tallest * 85:.0f}%"></i>'
        f"{c}{'+' if c == _MAX_CURVE_COST else ''}</div>"
        for c in range(_MAX_CURVE_COST + 1)
    )
    counter_rows = "".join(
        f'<div class="kv"><span>{label}</span><b>{counters[value]}</b></div>'
        for label, value in (("+2000 counter", 2000), ("+1000 counter", 1000), ("No counter", 0))
    )
    category_rows = "".join(
        f'<div class="kv"><span>{s}s</span><b>{categories[s]}</b></div>' for s in _SECTIONS
    )
    return (
        f'<section class="stats" style="--accent:{accent}">'
        f'<div class="panel"><h3>Cost curve</h3><div class="curve">{bars}</div></div>'
        f'<div class="panel"><h3>Counters</h3>{counter_rows}</div>'
        f'<div class="panel"><h3>Card types</h3>{category_rows}</div></section>'
    )


def _analysis(evaluation: EvaluationResult) -> str:
    # Claude's evaluation is model output, so every string is escaped like third-party data.
    panels = [
        ("Strengths", "var(--good)", evaluation.strengths),
        ("Weaknesses", "var(--bad)", evaluation.weaknesses),
        ("Suggestions", "var(--idea)", evaluation.suggestions),
    ]
    return (
        '<h2>Analysis</h2><section class="analysis">'
        + "".join(
            f'<div class="panel" style="--tone:{tone}"><h3>{title}</h3><ul>'
            + "".join(f"<li>{escape(item)}</li>" for item in items)
            + "</ul></div>"
            for title, tone, items in panels
        )
        + "</section>"
    )


def render_deck_html(
    leader: Card,
    entries: list[tuple[str, int]],
    cards: dict[str, Card],
    images: dict[str, str],
    evaluation: EvaluationResult | None = None,
) -> str:
    """Build the page. Every card ID in `entries` must be a key of `cards`."""
    total = sum(qty for _, qty in entries)
    accent = _COLOR_HEX.get(leader.colors[0], "#2f7fd8")
    sections = []
    for category in _SECTIONS:
        group = sorted(
            ((cid, qty) for cid, qty in entries if cards[cid].category == category),
            key=lambda e: (cards[e[0]].cost or 0, e[0]),
        )
        if group:
            count = sum(qty for _, qty in group)
            figures = "".join(_figure(cards[cid], images.get(cid), qty) for cid, qty in group)
            sections.append(
                f'<h2>{category}s &middot; {count}</h2><div class="grid">{figures}</div>'
            )
    title = f"{leader.id} {leader.name}"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body><main>\n"
        f"{_hero(leader, images.get(leader.id), evaluation)}\n"
        f"<h2>Deck &middot; {total} cards, {len(entries)} unique</h2>\n"
        f"{_stats(entries, cards, accent)}\n"
        f"{_analysis(evaluation) if evaluation is not None else ''}\n"
        + "\n".join(sections)
        + "\n<footer>Card data and images from optcgapi.com."
        + (" Analysis written by Claude." if evaluation is not None else "")
        + "</footer>\n</main></body></html>\n"
    )


def write_deck_page(
    leader_id: str,
    entries: list[tuple[str, int]],
    lookup: CardLookup,
    out_dir: Path,
    evaluation: EvaluationResult | None = None,
) -> Path:
    """Write the page for a deck whose card IDs are already known to be in the database."""
    ids = [leader_id, *(cid for cid, _ in entries)]
    cards = lookup.get_many(ids)
    html = render_deck_html(cards[leader_id], entries, cards, lookup.image_urls(ids), evaluation)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{leader_id}-{datetime.now():%Y%m%d-%H%M%S}.html"
    path.write_text(html, encoding="utf-8")
    return path


def open_in_browser(path: Path) -> bool:
    # False inside Docker, where there is no browser to open.
    try:
        return webbrowser.open(path.resolve().as_uri())
    except webbrowser.Error:
        return False
