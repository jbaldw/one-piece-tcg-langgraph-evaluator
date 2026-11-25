from typer.testing import CliRunner

from op_tcg_evaluator import cli
from op_tcg_evaluator.config import get_settings
from op_tcg_evaluator.deck_view import render_deck_html
from op_tcg_evaluator.graph import GeneratorState
from op_tcg_evaluator.models import Card, Decklist, EvaluationResult

# Matches the printings seeded in conftest.py.
IMAGE_BASE = "https://optcgapi.com/media/static/Card_Images/"
LEADER = "OP01-001"
DECK = [(f"OP01-{i:03d}", 4) for i in range(2, 14)] + [("OP01-014", 2)]
DECK_TEXT = LEADER + "\n" + "\n".join(f"{q}x{cid}" for cid, q in DECK) + "\n"


def test_image_urls_prefer_base_printing(cards):
    urls = cards.image_urls(["OP01-001", "OP01-002", "OP01-003", "OP01-004"])
    assert urls == {
        "OP01-001": f"{IMAGE_BASE}OP01-001.jpg",
        "OP01-002": f"{IMAGE_BASE}OP01-002.jpg",
        "OP01-003": f"{IMAGE_BASE}OP01-003_p1.jpg",
    }


def test_page_escapes_card_text_and_drops_foreign_images():
    leader = Card(id=LEADER, name="Zoro", category="Leader", color="Red")
    hostile = Card(
        id="OP01-002", name='<script>alert(1)</script>"', category="Character", color="Red"
    )
    html = render_deck_html(
        leader,
        [("OP01-002", 4)],
        {LEADER: leader, "OP01-002": hostile},
        {LEADER: "https://evil.example/x.jpg", "OP01-002": f"{IMAGE_BASE}OP01-002.jpg"},
    )
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;&quot;" in html
    assert "evil.example" not in html
    assert f'src="{IMAGE_BASE}OP01-002.jpg"' in html
    assert '<span class="qty">4x</span>' in html


def _use_test_db(cards, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(cards.db_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unused")
    monkeypatch.setenv("ANTHROPIC_MODEL", "unused")
    monkeypatch.setattr(cli, "open_in_browser", lambda path: False)
    get_settings.cache_clear()
    monkeypatch.setattr(cli, "get_settings", get_settings)


def test_show_writes_deck_page(cards, tmp_path, monkeypatch):
    _use_test_db(cards, monkeypatch)
    deck_file = tmp_path / "deck.txt"
    deck_file.write_text(DECK_TEXT, encoding="utf-8")

    result = CliRunner().invoke(cli.app, ["show", str(deck_file)])
    get_settings.cache_clear()

    assert result.exit_code == 0, result.output
    pages = list((cards.db_path.parent / "decks").glob(f"{LEADER}-*.html"))
    assert pages
    html = pages[-1].read_text(encoding="utf-8")
    assert "Roronoa Zoro" in html and "50 cards, 13 unique" in html


def test_show_rejects_unknown_cards(cards, tmp_path, monkeypatch):
    _use_test_db(cards, monkeypatch)
    deck_file = tmp_path / "deck.txt"
    deck_file.write_text(f"{LEADER}\n4xOP09-999\n", encoding="utf-8")

    result = CliRunner().invoke(cli.app, ["show", str(deck_file)])
    get_settings.cache_clear()

    assert result.exit_code == 1
    assert "OP09-999 is not in the card database" in result.output


def test_generate_show_keeps_stdout_a_clean_decklist(cards, monkeypatch):
    _use_test_db(cards, monkeypatch)
    deck = Decklist(leader_id=LEADER, cards=[{"card_id": cid, "quantity": q} for cid, q in DECK])

    class FakeGraph:
        def invoke(self, state):
            return GeneratorState(leader_id=LEADER, attempts=1, decklist=deck)

    monkeypatch.setattr(cli, "build_generator_graph", lambda cards: FakeGraph())
    result = CliRunner().invoke(cli.app, ["generate", LEADER, "--show"])
    get_settings.cache_clear()

    assert result.exit_code == 0, result.output
    assert result.stdout == DECK_TEXT
    assert "Deck page written to" in result.stderr


def test_show_reads_decklist_saved_by_powershell(cards, tmp_path, monkeypatch):
    _use_test_db(cards, monkeypatch)
    deck_file = tmp_path / "deck.txt"
    deck_file.write_bytes(b"\xef\xbb\xbf" + DECK_TEXT.replace("\n", "\r\n").encode())

    result = CliRunner().invoke(cli.app, ["show", str(deck_file)])
    get_settings.cache_clear()

    assert result.exit_code == 0, result.output


def _small_deck():
    leader = Card(id=LEADER, name="Zoro", category="Leader", color="Red", power=5000, life=5)
    nami = Card(id="OP01-016", name="Nami", category="Character", color="Red", cost=1, counter=1000)
    event = Card(id="OP01-029", name="Radical Beam!!", category="Event", color="Red", cost=1)
    cards = {LEADER: leader, nami.id: nami, event.id: event}
    return leader, [(nami.id, 4), (event.id, 2)], cards


def test_page_shows_escaped_analysis_and_score():
    leader, entries, cards = _small_deck()
    evaluation = EvaluationResult(
        score=72,
        strengths=["<img src=x onerror=alert(1)> strong curve"],
        weaknesses=["few blockers"],
        suggestions=["add 2000 counters"],
    )
    html = render_deck_html(leader, entries, cards, {}, evaluation)
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt; strong curve" in html
    assert "<h3>Weaknesses</h3><ul><li>few blockers</li>" in html
    assert "--pct:72" in html and "<b>72</b>" in html
    assert "Analysis written by Claude" in html


def test_page_without_evaluation_has_no_analysis():
    leader, entries, cards = _small_deck()
    html = render_deck_html(leader, entries, cards, {})
    assert "<h2>Analysis</h2>" not in html
    assert 'class="score"' not in html
    assert "Analysis written by Claude" not in html


def test_page_stats_count_quantities():
    leader, entries, cards = _small_deck()
    html = render_deck_html(leader, entries, cards, {})
    assert '<div class="kv"><span>+1000 counter</span><b>4</b></div>' in html
    assert '<div class="kv"><span>No counter</span><b>2</b></div>' in html
    assert '<div class="kv"><span>Events</span><b>2</b></div>' in html
    assert "<h2>Characters &middot; 4</h2>" in html
    assert "Deck &middot; 6 cards, 2 unique" in html
