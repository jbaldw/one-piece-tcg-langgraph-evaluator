"""Turn raw optcgapi printings into one clean record per card ID.

optcgapi returns one row per printing, and printings of the same card disagree: errata
notes, reprint tags in names, and outright junk (a cost of "Former Roger Pirates", a color
of "Character"). Values from the card's own base printing win; otherwise the most common
valid value does. Every disagreement is reported so bad source data stays visible.
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from importlib.resources import files

from op_tcg_evaluator.models import CardCategory

COLORS = ("Red", "Green", "Blue", "Purple", "Black", "Yellow")
ATTRIBUTES = ("Slash", "Strike", "Special", "Wisdom", "Ranged")
_MISSING = {"", "NULL", "N/A", "?", "-"}
_INVALID = object()

# Variant suffixes optcgapi copies from TCGPlayer listings, e.g. "Roronoa Zoro (001) (Parallel)".
# Character disambiguations such as "Mr.3 (Galdino)" are kept.
_VARIANT_TAG = re.compile(
    r"\s*\((?:\d{3}|[A-Z0-9]+-\d{3}|SPR?|TR"
    r"|[^)]*\b(?:Art|Parallel|Foil|Reprint|Manga|Topper|Pack|Poster|Leader)\b[^)]*)\)"
)
_PRINTING_SUFFIX = re.compile(r"_[a-z]\d+$")
_TYPE_IN_TEXT = re.compile(r"\{([^}]+)\}")


def card_id_of(row: dict) -> str:
    # A few promo rows carry the image suffix in card_set_id too (e.g. "P-030_r1").
    return _PRINTING_SUFFIX.sub("", row["card_set_id"])


def clean_name(name: str | None) -> str | None:
    if name is None:
        return None
    return _VARIANT_TAG.sub("", name).strip() or None


def _missing(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in _MISSING)


def parse_int(value):
    if _missing(value):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text) if text.isdigit() else _INVALID


def parse_colors(value):
    if _missing(value):
        return None
    parts = set(re.split(r"[\s/]+", value.strip()))
    if not parts <= set(COLORS):
        return _INVALID
    return tuple(c for c in COLORS if c in parts)


def parse_category(value):
    if _missing(value):
        return None
    return value if value in set(CardCategory) else _INVALID


def parse_attribute(value):
    # "?" is a printed attribute (e.g. Imu, OP13-079), not a placeholder for missing data.
    if isinstance(value, str) and value.strip() == "?":
        return "?"
    if _missing(value):
        return None
    parts = [p for p in re.split(r"[\s/]+", value.strip()) if p]
    if not set(parts) <= set(ATTRIBUTES):
        return _INVALID
    return "/".join(a for a in ATTRIBUTES if a in parts)


def parse_power(value):
    # Printed power is always in thousands; anything else is a column-shifted source row.
    power = parse_int(value)
    return _INVALID if isinstance(power, int) and power % 1000 else power


def parse_text(value):
    return None if _missing(value) else value.strip()


def parse_sub_types(value):
    # Like the attribute, Imu's printed type is "?".
    if isinstance(value, str) and value.strip() == "?":
        return "?"
    text = parse_text(value)
    return _INVALID if text is not None and text.isdigit() else text


# Canonical field -> (raw API key, parser).
_FIELDS = {
    "name": ("card_name", clean_name),
    "category": ("card_type", parse_category),
    "colors": ("card_color", parse_colors),
    "cost": ("card_cost", parse_int),
    "power": ("card_power", parse_power),
    "counter": ("counter_amount", parse_int),
    "life": ("life", parse_int),
    "attribute": ("attribute", parse_attribute),
    "card_text": ("card_text", parse_text),
    "types_raw": ("sub_types", parse_sub_types),
}
_REQUIRED = ("name", "category", "colors")


@dataclass
class CanonicalCard:
    id: str
    name: str
    category: str
    colors: tuple[str, ...]
    cost: int | None
    power: int | None
    counter: int | None
    life: int | None
    attribute: str | None
    card_text: str | None
    types_raw: str | None
    types: list[str]
    set_code: str


@dataclass
class Conflict:
    card_id: str
    field: str
    chosen: str
    alternatives: list[str]


@dataclass
class ImportReport:
    conflicts: list[Conflict] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    guessed_types: set[str] = field(default_factory=set)


def _is_base_printing(card_id: str, row: dict) -> bool:
    # OP01-001 printed in set "OP-01" under its own image id, i.e. not a parallel or reprint.
    set_id = (row.get("set_id") or "").replace("-", "")
    return row.get("card_image_id") == card_id and set_id == card_id.split("-")[0]


def _is_clean(row: dict) -> bool:
    return all(parser(row.get(key)) is not _INVALID for key, parser in _FIELDS.values())


def _preference_tiers(card_id: str, rows: list[dict]) -> list[list[dict]]:
    # A printing with any unparseable field is likely a shifted row, so none of its
    # values outrank a clean printing's, even if it is the base printing.
    clean = [r for r in rows if _is_clean(r)]
    return [
        [r for r in clean if _is_base_printing(card_id, r)],
        [r for r in clean if r.get("card_image_id") == card_id],
        clean,
        rows,
    ]


def _choose(card_id: str, name: str, rows: list[dict], report: ImportReport):
    raw_key, parser = _FIELDS[name]
    parsed = [(r, parser(r.get(raw_key))) for r in rows]
    valid = [v for _, v in parsed if v is not None and v is not _INVALID]

    chosen = None
    for tier in _preference_tiers(card_id, rows):
        tier_ids = {id(r) for r in tier}
        values = [v for r, v in parsed if id(r) in tier_ids and v is not None and v is not _INVALID]
        if values:
            chosen = Counter(values).most_common(1)[0][0]
            break

    distinct = set(valid)
    if len(distinct) > 1:
        report.conflicts.append(
            Conflict(card_id, name, str(chosen), sorted(str(v) for v in distinct - {chosen}))
        )
    return chosen


def _segment(words: list[str], vocab: set[str]) -> list[str] | None:
    """Split words into the fewest vocabulary entries, or None if they cannot be covered."""
    best: list[list[str] | None] = [None] * (len(words) + 1)
    best[0] = []
    for i in range(len(words)):
        if best[i] is None:
            continue
        for j in range(i + 1, len(words) + 1):
            piece = " ".join(words[i:j])
            if piece in vocab and (best[j] is None or len(best[i]) + 1 < len(best[j])):
                best[j] = best[i] + [piece]
    return best[-1]


def _single_unknown_chunk(words: list[str], vocab: set[str]) -> str | None:
    """The shortest run of words that, if it were a type, would make the rest segmentable.

    A one-word chunk must already stand alone somewhere, or "Former Navy" would yield a
    "Former" type; such strings are learned whole instead.
    """
    n = len(words)
    for size in range(2, n):
        for i in range(n - size + 1):
            j = i + size
            if _segment(words[:i], vocab) is not None and _segment(words[j:], vocab) is not None:
                return " ".join(words[i:j])
    return None


@dataclass
class TypeOverrides:
    """Hand-checked corrections from type_overrides.json."""

    splits: dict[str, list[str]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "TypeOverrides":
        data = json.loads(
            files("op_tcg_evaluator.db").joinpath("type_overrides.json").read_text(encoding="utf-8")
        )
        return cls(splits=data["splits"], aliases=data["aliases"])


def build_type_vocab(
    sub_types: list[str], card_texts: list[str], overrides: TypeOverrides | None = None
) -> tuple[set[str], set[str]]:
    """Return (vocabulary, types that were inferred rather than seen delimited).

    Types are confirmed by "/"-separated sub_types rows, by {Type} references in card
    text, and by the overrides file. The rest are inferred shortest-string-first, so
    "Celestial Dragons" is learned whole before "Celestial Dragons Five Elders" is split
    against it.
    """
    overrides = overrides or TypeOverrides()
    vocab = {p.strip() for s in sub_types if "/" in s for p in s.split("/") if p.strip()}
    vocab |= {m.strip() for t in card_texts for m in _TYPE_IN_TEXT.findall(t)}
    vocab |= {t for types in overrides.splits.values() for t in types}
    vocab |= set(overrides.aliases)
    guessed: set[str] = set()
    spaced = {
        s.strip() for s in sub_types if s.strip() and "/" not in s and s not in overrides.splits
    }
    for s in sorted(spaced, key=lambda s: (len(s.split()), s)):
        words = s.split()
        if _segment(words, vocab) is not None:
            continue
        new = _single_unknown_chunk(words, vocab) or s
        vocab.add(new)
        guessed.add(new)
    return vocab, guessed


def split_types(
    sub_types: str | None, vocab: set[str], overrides: TypeOverrides | None = None
) -> list[str]:
    overrides = overrides or TypeOverrides()
    if not sub_types:
        return []
    if sub_types in overrides.splits:
        parts = overrides.splits[sub_types]
    elif "/" in sub_types:
        parts = [p.strip() for p in sub_types.split("/")]
    else:
        parts = _segment(sub_types.split(), vocab) or [sub_types.strip()]
    return list(dict.fromkeys(overrides.aliases.get(p, p) for p in parts if p))


def canonicalize(
    rows: list[dict], overrides: TypeOverrides | None = None
) -> tuple[list[CanonicalCard], ImportReport]:
    overrides = overrides if overrides is not None else TypeOverrides.load()
    report = ImportReport()
    by_id: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_id[card_id_of(row)].append(row)

    vocab, report.guessed_types = build_type_vocab(
        [
            t
            for r in rows
            if (t := parse_sub_types(r.get("sub_types"))) is not None and t is not _INVALID
        ],
        [r["card_text"] for r in rows if not _missing(r.get("card_text"))],
        overrides,
    )
    # Alias targets (e.g. "FILM") are real types, not guesses.
    report.guessed_types -= set(overrides.aliases) | set(overrides.aliases.values())

    cards = []
    for card_id in sorted(by_id):
        values = {name: _choose(card_id, name, by_id[card_id], report) for name in _FIELDS}
        missing = [name for name in _REQUIRED if values[name] is None]
        if missing:
            report.skipped.append((card_id, f"no valid {', '.join(missing)}"))
            continue
        cards.append(
            CanonicalCard(
                id=card_id,
                types=split_types(values["types_raw"], vocab, overrides),
                set_code=card_id.split("-")[0],
                **values,
            )
        )
    return cards, report
