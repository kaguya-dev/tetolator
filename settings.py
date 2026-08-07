"""Settings helpers for Tetolator.

Settings are stored as key/value rows in the `settings` table and are
used to drive the automatic cost calculation. Every key has a sensible
default, so the app works even before the user opens the Settings tab.
"""

from __future__ import annotations

from typing import Any

from database import get_connection

DEFAULTS: dict[str, Any] = {
    "currency": "$",
    "cost_per_hour": 0.0,       # electricity / machine depreciation
    "markup_percent": 0.0,      # applied on top of the subtotal
}

# Keys that should be returned as numbers, not strings.
NUMERIC_KEYS = {"cost_per_hour", "markup_percent"}


def get_settings() -> dict[str, Any]:
    """Return all settings merged over the defaults."""
    settings = dict(DEFAULTS)
    conn = get_connection()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for row in rows:
            settings[row["key"]] = row["value"]
    finally:
        conn.close()
    return coerce_types(settings)


def coerce_types(settings: dict[str, Any]) -> dict[str, Any]:
    """Convert numeric keys to float so math works safely."""
    for key in NUMERIC_KEYS:
        settings[key] = float(settings[key] or 0)
    return settings


def update_settings(new_values: dict[str, Any]) -> dict[str, Any]:
    """Persist the given key/value pairs and return the updated settings."""
    conn = get_connection()
    try:
        for key, value in new_values.items():
            if key not in DEFAULTS:
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
        conn.commit()
    finally:
        conn.close()
    return get_settings()
