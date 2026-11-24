CREATE TABLE IF NOT EXISTS cards (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL CHECK (category IN ('Leader', 'Character', 'Event', 'Stage')),
    color     TEXT NOT NULL,
    cost      INTEGER,
    power     INTEGER,
    counter   INTEGER,
    set_code  TEXT
);

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
