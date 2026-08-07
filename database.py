"""Database layer for Tetolator.

Responsible for:
- Creating the SQLite file and schema on first run.
- Providing a connection helper for the rest of the app.
- Keeping the schema in one place for easy future migrations.

The database file lives in `data/tetolator.db` and is created
automatically on startup.
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "tetolator.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS filaments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    brand          TEXT NOT NULL DEFAULT '',
    material       TEXT NOT NULL DEFAULT 'PLA',
    color          TEXT NOT NULL DEFAULT '',
    spool_weight_g REAL NOT NULL DEFAULT 1000,
    price          REAL NOT NULL DEFAULT 0,
    notes          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prints (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    INTEGER,
    model_name   TEXT NOT NULL,
    filament_id  INTEGER,
    weight_used_g REAL NOT NULL DEFAULT 0,
    hours        INTEGER NOT NULL DEFAULT 0,
    minutes      INTEGER NOT NULL DEFAULT 0,
    print_date   TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    -- Cost snapshot saved at creation time so later changes to
    -- filament prices or settings never rewrite history.
    filament_cost REAL NOT NULL DEFAULT 0,
    time_cost     REAL NOT NULL DEFAULT 0,
    markup        REAL NOT NULL DEFAULT 0,
    total_cost    REAL NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (client_id)   REFERENCES clients(id)   ON DELETE SET NULL,
    FOREIGN KEY (filament_id) REFERENCES filaments(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row access by name."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the database file and tables if they do not exist yet."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
