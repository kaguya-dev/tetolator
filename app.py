"""Tetolator - a local-first web app for logging 3D printed parts.

Run with:
    python app.py

The server binds to 0.0.0.0 so other machines on your local network can
reach it (e.g. http://<your-ip>:5000). It is not exposed to the internet.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

import backup
import models
from database import init_db
from settings import get_settings, update_settings

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
app.json.sort_keys = False


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Clients / Projects
# ---------------------------------------------------------------------------

@app.get("/api/clients")
def api_list_clients():
    return jsonify(models.list_clients())


@app.post("/api/clients")
def api_create_client():
    data = request.get_json(silent=True) or {}
    if not data.get("name", "").strip():
        return jsonify({"error": "Client name is required."}), 400
    return jsonify(models.create_client(data)), 201


@app.put("/api/clients/<int:client_id>")
def api_update_client(client_id):
    data = request.get_json(silent=True) or {}
    if not data.get("name", "").strip():
        return jsonify({"error": "Client name is required."}), 400
    client = models.update_client(client_id, data)
    if client is None:
        return jsonify({"error": "Client not found."}), 404
    return jsonify(client)


@app.delete("/api/clients/<int:client_id>")
def api_delete_client(client_id):
    if models.delete_client(client_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Client not found."}), 404


# ---------------------------------------------------------------------------
# Filament profiles
# ---------------------------------------------------------------------------

@app.get("/api/filaments")
def api_list_filaments():
    return jsonify(models.list_filaments())


@app.post("/api/filaments")
def api_create_filament():
    data = request.get_json(silent=True) or {}
    if not data.get("name", "").strip():
        return jsonify({"error": "Filament name is required."}), 400
    return jsonify(models.create_filament(data)), 201


@app.put("/api/filaments/<int:filament_id>")
def api_update_filament(filament_id):
    data = request.get_json(silent=True) or {}
    if not data.get("name", "").strip():
        return jsonify({"error": "Filament name is required."}), 400
    filament = models.update_filament(filament_id, data)
    if filament is None:
        return jsonify({"error": "Filament not found."}), 404
    return jsonify(filament)


@app.delete("/api/filaments/<int:filament_id>")
def api_delete_filament(filament_id):
    if models.delete_filament(filament_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Filament not found."}), 404


# ---------------------------------------------------------------------------
# Prints
# ---------------------------------------------------------------------------

@app.get("/api/prints")
def api_list_prints():
    return jsonify(models.list_prints())


@app.post("/api/prints")
def api_create_print():
    data = request.get_json(silent=True) or {}
    if not data.get("model_name", "").strip():
        return jsonify({"error": "Model name is required."}), 400
    if not data.get("print_date"):
        return jsonify({"error": "Print date is required."}), 400
    return jsonify(models.create_print(data)), 201


@app.put("/api/prints/<int:print_id>")
def api_update_print(print_id):
    data = request.get_json(silent=True) or {}
    if not data.get("model_name", "").strip():
        return jsonify({"error": "Model name is required."}), 400
    if not data.get("print_date"):
        return jsonify({"error": "Print date is required."}), 400
    record = models.update_print(print_id, data)
    if record is None:
        return jsonify({"error": "Print record not found."}), 404
    return jsonify(record)


@app.delete("/api/prints/<int:print_id>")
def api_delete_print(print_id):
    if models.delete_print(print_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Print record not found."}), 404


@app.post("/api/prints/preview-cost")
def api_preview_cost():
    """Return the cost breakdown for a record without saving it."""
    data = request.get_json(silent=True) or {}
    return jsonify(models.compute_costs(data))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def api_get_settings():
    return jsonify(get_settings())


@app.put("/api/settings")
def api_update_settings():
    data = request.get_json(silent=True) or {}
    return jsonify(update_settings(data))


# ---------------------------------------------------------------------------
# Backup / restore
# ---------------------------------------------------------------------------

@app.get("/api/backup/export")
def api_backup_export():
    """Download a ZIP with one CSV per table."""
    return send_file(
        io.BytesIO(backup.export_zip()),
        mimetype="application/zip",
        as_attachment=True,
        download_name=backup.backup_filename(),
    )


@app.get("/api/backup/export/<table>")
def api_backup_export_table(table):
    """Download a single table as CSV (e.g. /api/backup/export/prints)."""
    if not backup.safe_table_name(table):
        return jsonify({"error": "Unknown table."}), 404
    return send_file(
        io.BytesIO(backup.export_table(table).encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{table}.csv",
    )


@app.post("/api/backup/import")
def api_backup_import():
    """Restore from an uploaded ZIP backup file."""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded."}), 400
    try:
        counts = backup.import_zip(file.read())
    except Exception as exc:  # noqa: BLE001 - surface any parse failure
        return jsonify({"error": f"Import failed: {exc}"}), 400
    return jsonify({"ok": True, "imported": counts})


@app.post("/api/backup/import/<table>")
def api_backup_import_table(table):
    """Restore a single table from an uploaded CSV file."""
    if not backup.safe_table_name(table):
        return jsonify({"error": "Unknown table."}), 404
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded."}), 400
    try:
        content = file.read().decode("utf-8")
        count = backup.import_table(table, content)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Import failed: {exc}"}), 400
    return jsonify({"ok": True, "table": table, "rows": count})


# ---------------------------------------------------------------------------

def main():
    init_db()
    host = os.environ.get("TETOLATOR_HOST", "0.0.0.0")
    port = int(os.environ.get("TETOLATOR_PORT", "5000"))
    print(f"* Tetolator running at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
