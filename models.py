"""Data access layer (CRUD) for Tetolator.

Every function here talks to the SQLite database through
`database.get_connection()`. All entities are converted to plain dicts
before being returned, so the Flask layer never leaks Row objects.

This module is the single place to touch when adding fields or new
query features.
"""

from __future__ import annotations

from typing import Any

from database import get_connection
from settings import get_settings

# ---------------------------------------------------------------------------
# Clients / Projects
# ---------------------------------------------------------------------------

def list_clients() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_client(client_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def create_client(data: dict[str, Any]) -> dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO clients (name, notes) VALUES (?, ?)",
            (data.get("name", "").strip(), data.get("notes", "")),
        )
        conn.commit()
        return get_client(cur.lastrowid)  # type: ignore[arg-type]
    finally:
        conn.close()


def update_client(client_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE clients SET name = ?, notes = ? WHERE id = ?",
            (data.get("name", "").strip(), data.get("notes", ""), client_id),
        )
        conn.commit()
        return get_client(client_id) if cur.rowcount else None
    finally:
        conn.close()


def delete_client(client_id: int) -> bool:
    """Delete a client. Linked prints keep existing (client set to NULL)."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Filament profiles
# ---------------------------------------------------------------------------

FILAMENT_FIELDS = (
    "name", "brand", "material", "color",
    "spool_weight_g", "price", "notes",
)


def list_filaments() -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM filaments ORDER BY name").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_filament(filament_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM filaments WHERE id = ?", (filament_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _filament_params(data: dict[str, Any]) -> tuple:
    return (
        data.get("name", "").strip(),
        data.get("brand", ""),
        data.get("material", "PLA"),
        data.get("color", ""),
        float(data.get("spool_weight_g") or 0),
        float(data.get("price") or 0),
        data.get("notes", ""),
    )


def create_filament(data: dict[str, Any]) -> dict[str, Any]:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO filaments "
            "(name, brand, material, color, spool_weight_g, price, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            _filament_params(data),
        )
        conn.commit()
        return get_filament(cur.lastrowid)  # type: ignore[arg-type]
    finally:
        conn.close()


def update_filament(filament_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE filaments SET name = ?, brand = ?, material = ?, "
            "color = ?, spool_weight_g = ?, price = ?, notes = ? WHERE id = ?",
            _filament_params(data) + (filament_id,),
        )
        conn.commit()
        return get_filament(filament_id) if cur.rowcount else None
    finally:
        conn.close()


def delete_filament(filament_id: int) -> bool:
    """Delete a filament. Linked prints keep existing (filament set to NULL)."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM filaments WHERE id = ?", (filament_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Prints
# ---------------------------------------------------------------------------

def list_prints() -> list[dict[str, Any]]:
    """Return prints joined with their client and filament for display."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.*, c.name AS client_name, f.name AS filament_name
            FROM prints p
            LEFT JOIN clients c   ON c.id = p.client_id
            LEFT JOIN filaments f ON f.id = p.filament_id
            ORDER BY p.print_date DESC, p.id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_print(print_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM prints WHERE id = ?", (print_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def compute_costs(data: dict[str, Any]) -> dict[str, float]:
    """Calculate the cost snapshot for a print record.

    formula:
        filament_cost = weight_g / 1000 * price_per_kg
        time_cost     = (hours + minutes/60) * cost_per_hour
        subtotal      = filament_cost + time_cost
        total         = subtotal * (1 + markup_percent/100)
        markup        = total - subtotal
    """
    settings = get_settings()

    weight_g = float(data.get("weight_used_g") or 0)
    hours = float(data.get("hours") or 0)
    minutes = float(data.get("minutes") or 0)

    price_per_kg = 0.0
    filament_id = data.get("filament_id")
    if filament_id:
        filament = get_filament(int(filament_id))
        if filament and filament["spool_weight_g"]:
            price_per_kg = filament["price"] / (filament["spool_weight_g"] / 1000)

    filament_cost = (weight_g / 1000) * price_per_kg
    time_cost = (hours + minutes / 60) * settings["cost_per_hour"]
    subtotal = filament_cost + time_cost
    total = subtotal * (1 + settings["markup_percent"] / 100)

    return {
        "filament_cost": round(filament_cost, 2),
        "time_cost": round(time_cost, 2),
        "markup": round(total - subtotal, 2),
        "total_cost": round(total, 2),
    }


def create_print(data: dict[str, Any]) -> dict[str, Any]:
    costs = compute_costs(data)
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO prints
                (client_id, model_name, filament_id, weight_used_g,
                 hours, minutes, print_date, notes,
                 filament_cost, time_cost, markup, total_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _int_or_none(data.get("client_id")),
                data.get("model_name", "").strip(),
                _int_or_none(data.get("filament_id")),
                float(data.get("weight_used_g") or 0),
                int(data.get("hours") or 0),
                int(data.get("minutes") or 0),
                data.get("print_date", ""),
                data.get("notes", ""),
                costs["filament_cost"],
                costs["time_cost"],
                costs["markup"],
                costs["total_cost"],
            ),
        )
        conn.commit()
        return get_print(cur.lastrowid)  # type: ignore[arg-type]
    finally:
        conn.close()


def update_print(print_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    costs = compute_costs(data)
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE prints SET
                client_id = ?, model_name = ?, filament_id = ?,
                weight_used_g = ?, hours = ?, minutes = ?,
                print_date = ?, notes = ?,
                filament_cost = ?, time_cost = ?, markup = ?, total_cost = ?
            WHERE id = ?
            """,
            (
                _int_or_none(data.get("client_id")),
                data.get("model_name", "").strip(),
                _int_or_none(data.get("filament_id")),
                float(data.get("weight_used_g") or 0),
                int(data.get("hours") or 0),
                int(data.get("minutes") or 0),
                data.get("print_date", ""),
                data.get("notes", ""),
                costs["filament_cost"],
                costs["time_cost"],
                costs["markup"],
                costs["total_cost"],
                print_id,
            ),
        )
        conn.commit()
        return get_print(print_id) if cur.rowcount else None
    finally:
        conn.close()


def delete_print(print_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM prints WHERE id = ?", (print_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
