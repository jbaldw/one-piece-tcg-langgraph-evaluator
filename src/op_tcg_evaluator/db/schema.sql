-- One cleaned row per card ID, built from card_printings by `op-eval seed`.
CREATE TABLE IF NOT EXISTS cards (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL CHECK (category IN ('Leader', 'Character', 'Event', 'Stage')),
    color      TEXT NOT NULL,
    cost       INTEGER,
    power      INTEGER,
    counter    INTEGER,
    set_code   TEXT,
    life       INTEGER,
    attribute  TEXT,
    card_text  TEXT,
    types_raw  TEXT
);

-- Colors and types get their own tables so legality rules are plain joins, not LIKE matches.
CREATE TABLE IF NOT EXISTS card_colors (
    card_id TEXT NOT NULL REFERENCES cards (id) ON DELETE CASCADE,
    color   TEXT NOT NULL CHECK (color IN ('Red', 'Green', 'Blue', 'Purple', 'Black', 'Yellow')),
    PRIMARY KEY (card_id, color)
);

CREATE TABLE IF NOT EXISTS card_types (
    card_id TEXT NOT NULL REFERENCES cards (id) ON DELETE CASCADE,
    type    TEXT NOT NULL,
    PRIMARY KEY (card_id, type)
);

CREATE INDEX IF NOT EXISTS idx_card_colors_color ON card_colors (color);
CREATE INDEX IF NOT EXISTS idx_card_types_type ON card_types (type);

-- Every optcgapi row as returned (parallels and reprints share a card_id). No FK to cards,
-- so a printing whose card could not be canonicalized is still kept for inspection.
-- image_id is not unique: reprints in other products (e.g. PRB-01) reuse the original image.
CREATE TABLE IF NOT EXISTS card_printings (
    id              INTEGER PRIMARY KEY,
    image_id        TEXT NOT NULL,
    card_id         TEXT NOT NULL,
    source          TEXT NOT NULL,
    name            TEXT,
    set_id          TEXT,
    set_name        TEXT,
    rarity          TEXT,
    color           TEXT,
    category        TEXT,
    cost            TEXT,
    power           TEXT,
    counter         TEXT,
    life            TEXT,
    attribute       TEXT,
    sub_types       TEXT,
    card_text       TEXT,
    market_price    REAL,
    inventory_price REAL,
    image_url       TEXT,
    date_scraped    TEXT
);

CREATE INDEX IF NOT EXISTS idx_card_printings_card_id ON card_printings (card_id);

CREATE TABLE IF NOT EXISTS decks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    leader_id  TEXT NOT NULL REFERENCES cards (id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id  INTEGER NOT NULL REFERENCES decks (id) ON DELETE CASCADE,
    card_id  TEXT NOT NULL REFERENCES cards (id),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 4),
    PRIMARY KEY (deck_id, card_id)
);
