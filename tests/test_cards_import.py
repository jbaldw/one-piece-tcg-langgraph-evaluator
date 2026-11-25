from op_tcg_evaluator.db.connection import get_connection, init_db
from op_tcg_evaluator.db.normalize import (
    TypeOverrides,
    build_type_vocab,
    canonicalize,
    clean_name,
    parse_colors,
    split_types,
)
from op_tcg_evaluator.db.seed import load_cards


def _row(card_id, image_id=None, set_id=None, **overrides):
    row = {
        "card_set_id": card_id,
        "card_image_id": image_id or card_id,
        "set_id": set_id or card_id.split("-")[0][:-2] + "-" + card_id.split("-")[0][-2:],
        "card_name": "Roronoa Zoro (001)",
        "card_type": "Character",
        "card_color": "Red",
        "card_cost": "3",
        "card_power": "5000",
        "counter_amount": 1000,
        "life": None,
        "attribute": "Slash",
        "sub_types": "Straw Hat Crew",
        "card_text": "",
        "rarity": "C",
        "market_price": 0.1,
    }
    row.update(overrides)
    return row


def test_clean_name_strips_variant_tags_only():
    assert clean_name("Roronoa Zoro (001) (Parallel)") == "Roronoa Zoro"
    assert clean_name("Brook (Reprint)") == "Brook"
    assert clean_name("Mr.3 (Galdino)") == "Mr.3 (Galdino)"


def test_parse_colors_handles_multicolor_and_junk():
    assert parse_colors("Purple Blue") == ("Blue", "Purple")
    assert parse_colors("NULL") is None
    assert parse_colors("Character") is not None and not isinstance(
        parse_colors("Character"), tuple
    )


def test_question_mark_is_a_real_attribute_and_type():
    cards, _ = canonicalize([_row("OP13-079", card_type="Leader", attribute="?", sub_types="?")])
    assert cards[0].attribute == "?"
    assert cards[0].types == ["?"]


def test_base_printing_wins_over_majority():
    rows = [
        _row("OP01-016", counter_amount=1000),
        _row("OP01-016", image_id="OP01-016_p1", counter_amount=2000),
        _row("OP01-016", set_id="PRB-01", counter_amount=2000),
    ]
    cards, report = canonicalize(rows)
    assert cards[0].counter == 1000
    assert [(c.field, c.chosen) for c in report.conflicts] == [("counter", "1000")]


def test_invalid_base_value_falls_back_to_other_printings():
    rows = [
        _row("OP04-095", card_color="Character", card_cost="Former Roger Pirates"),
        _row("OP04-095", image_id="OP04-095_p1", card_color="Black", card_cost="4"),
    ]
    cards, _ = canonicalize(rows)
    assert cards[0].colors == ("Black",)
    assert cards[0].cost == 4


def test_shifted_base_printing_loses_every_field():
    # Mirrors OP08-001 in the real data: the base row's columns are shifted by one.
    rows = [
        _row("OP08-001", card_type="Leader", card_power="4", life="1", sub_types="5000"),
        _row(
            "OP08-001",
            image_id="OP08-001_p1",
            card_type="Leader",
            card_power="5000",
            life="4",
            sub_types="Animal Straw Hat Crew",
        ),
    ]
    cards, _ = canonicalize(rows)
    assert (cards[0].power, cards[0].life) == (5000, 4)
    assert cards[0].types_raw == "Animal Straw Hat Crew"


def test_card_without_valid_color_is_skipped():
    cards, report = canonicalize([_row("OP01-002", card_color="NULL")])
    assert cards == []
    assert report.skipped == [("OP01-002", "no valid colors")]


def test_type_vocab_splits_space_separated_types():
    sub_types = [
        "Celestial Dragons",
        "Celestial Dragons Five Elders",
        "Donquixote Pirates/The Seven Warlords of the Sea",
        "Donquixote Pirates The Seven Warlords of the Sea",
    ]
    vocab, guessed = build_type_vocab(sub_types, ["Your {Straw Hat Crew} type Characters"])
    assert split_types("Celestial Dragons Five Elders", vocab) == [
        "Celestial Dragons",
        "Five Elders",
    ]
    assert split_types("Donquixote Pirates The Seven Warlords of the Sea", vocab) == [
        "Donquixote Pirates",
        "The Seven Warlords of the Sea",
    ]
    assert guessed == {"Celestial Dragons", "Five Elders"}


def test_shipped_overrides_fix_verified_splits():
    rows = [
        _row("OP10-050", sub_types="Giant Dressrosa New Giant Pirates"),
        _row("OP03-100", sub_types="Big Mom Pirates Homies"),
        _row("OP01-005", sub_types="Film"),
    ]
    cards, report = canonicalize(rows)
    assert [sorted(c.types) for c in cards] == [
        ["FILM"],
        ["Big Mom Pirates", "Homies"],
        ["Dressrosa", "Giant", "New Giant Pirates"],
    ]
    assert "Film" not in report.guessed_types


def test_aliases_apply_inside_inferred_splits():
    overrides = TypeOverrides(aliases={"New Giant Pirate Crew": "New Giant Pirates"})
    vocab, _ = build_type_vocab(["Giant/Dressrosa"], [], overrides)
    assert split_types("Giant New Giant Pirate Crew Dressrosa", vocab, overrides) == [
        "Giant",
        "New Giant Pirates",
        "Dressrosa",
    ]


def test_type_vocab_keeps_one_word_prefixes_attached():
    vocab, guessed = build_type_vocab(["Navy", "Former Navy"], [])
    assert split_types("Former Navy", vocab) == ["Former Navy"]
    assert "Former" not in guessed


def test_load_cards_populates_lookup_tables(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    rows = {
        "set": [
            _row(
                "OP01-001",
                card_type="Leader",
                card_color="Red Green",
                life="5",
                card_cost=None,
                counter_amount=None,
            ),
            _row(
                "OP01-001",
                image_id="OP01-001_p1",
                card_type="Leader",
                card_color="Red Green",
                life="5",
                card_cost=None,
                counter_amount=None,
            ),
        ],
        "starter": [_row("ST01-002", card_color="Green", sub_types="Straw Hat Crew")],
    }
    with get_connection(db) as conn:
        load_cards(conn, rows)
        load_cards(conn, rows)  # reseeding must replace, not duplicate
        assert conn.execute("SELECT COUNT(*) FROM card_printings").fetchone()[0] == 3
        leader = conn.execute("SELECT * FROM cards WHERE id = 'OP01-001'").fetchone()
        assert (leader["color"], leader["life"], leader["name"]) == ("Red/Green", 5, "Roronoa Zoro")
        # Cards sharing at least one color with the leader.
        playable = conn.execute(
            """
            SELECT DISTINCT cc.card_id FROM card_colors cc
            JOIN card_colors lc ON lc.color = cc.color AND lc.card_id = 'OP01-001'
            WHERE cc.card_id != 'OP01-001'
            """
        ).fetchall()
        assert [r[0] for r in playable] == ["ST01-002"]
        types = conn.execute("SELECT type FROM card_types WHERE card_id = 'ST01-002'").fetchall()
        assert [r[0] for r in types] == ["Straw Hat Crew"]
