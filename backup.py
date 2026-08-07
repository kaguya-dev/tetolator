"""Backup / restore for Tetolator.

The backup is a ZIP file containing one CSV per table:

    tetolator-backup-YYYY-MM-DD.zip
    ├── clients.csv
    ├── filaments.csv
    ├── prints.csv
    └── settings.csv

CSV was chosen so backups are human-readable and can be opened in any
spreadsheet or text editor. Restoring replaces the current data.

Import accepts either the ZIP file or a set of individual CSVs with the
exact same names.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any
from zipfile import ZipFile

from database import get_connection

CSV_FILES = ("clients", "filaments", "prints", "settings")

# Maps each CSV back to its table. `settings` needs a plain dict read/write
# because it is key/value, not a list of rows.
TABLE_NAMES = {"clients": "clients", "filaments": "filaments", "prints": "prints"}


def _settings_to_csv() -> str:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    finally:
        conn.close()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["key", "value"])
    writer.writerows([(r["key"], r["value"]) for r in rows])
    return buf.getvalue()


def _settings_from_csv(content: str) -> None:
    reader = csv.DictReader(io.StringIO(content))
    conn = get_connection()
    try:
        for row in reader:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (row["key"], row["value"]),
            )
        conn.commit()
    finally:
        conn.close()


def _rows_to_csv(table: str) -> str:
    conn = get_connection()
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()
    buf = io.StringIO()
    writer = csv.writer(buf)
    if rows:
        writer.writerow(rows[0].keys())
        writer.writerows([list(r) for r in rows])
    return buf.getvalue()


def export_zip() -> bytes:
    """Return the bytes of a ZIP backup containing all tables as CSV."""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as zf:
        for table in TABLE_NAMES:
            zf.writestr(f"{table}.csv", _rows_to_csv(table))
        zf.writestr("settings.csv", _settings_to_csv())
    return buffer.getvalue()


def export_table(table: str) -> str:
    """Return one table's CSV as text (used for single-table download)."""
    if table == "settings":
        return _settings_to_csv()
    return _rows_to_csv(table)


def import_zip(data: bytes) -> dict[str, int]:
    """Restore the database from a backup ZIP. Returns {table: row_count}."""
    counts: dict[str, int] = {}
    with ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        for table in CSV_FILES:
            if f"{table}.csv" not in names:
                continue
            content = zf.read(f"{table}.csv").decode("utf-8")
            counts[table] = _import_table(table, content)
    return counts


def import_table(table: str, content: str) -> int:
    """Restore a single table from raw CSV text."""
    return _import_table(table, content)


def _import_table(table: str, content: str) -> int:
    """Replace the contents of `table` with the rows parsed from CSV."""
    if table == "settings":
        _settings_from_csv(content)
        return len(list(csv.DictReader(io.StringIO(content))))

    conn = get_connection()
    try:
        conn.execute(f"DELETE FROM {table}")
        reader = csv.DictReader(io.StringIO(content))
        count = 0
        for row in reader:
            columns = [k for k in row.keys() if k is not None]
            placeholders = ", ".join("?" for _ in columns)
            quoted = ", ".join(f'"{c}"' for c in columns)
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({quoted}) VALUES ({placeholders})",
                [_clean(row[c]) for c in columns],
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def _clean(value: Any) -> Any:
    """Trim stray whitespace that some editors add to CSV cells."""
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    return value


def backup_filename() -> str:
    import datetime

    return "tetolator-backup-" + datetime.date.today().isoformat() + ".zip"


def safe_table_name(table: str) -> bool:
    """Guard against SQL injection via table names."""
    return table in TABLE_NAMES or table == "settings"
