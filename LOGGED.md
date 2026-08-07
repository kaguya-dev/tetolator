# Tetolator - Technical Log

This document explains how Tetolator works internally: the architecture, each
file's role, how data flows, and where to look when extending the project.
It is written for developers (human or AI) who need to read and modify the
codebase quickly.

## Overview

Tetolator is a **local-first** web application. A Python Flask server exposes a
small REST/JSON API and also serves the static frontend. Data lives in a single
SQLite file. There is no build step, no ORM, and no authentication - by design,
it only runs on the user's local network.

```
Browser (static HTML/CSS/JS)
        │  fetch() JSON
        ▼
Flask app.py  ──►  models.py  ──►  SQLite (data/tetolator.db)
        │              ▲
        └── backup.py ─┘
```

## Where things run

| Layer | Location | Tech |
|---|---|---|
| HTTP server + API | `app.py` | Flask |
| Database schema/connection | `database.py` | stdlib `sqlite3` |
| Business logic (CRUD, cost math) | `models.py` | plain functions |
| Settings persistence | `settings.py` | key/value rows |
| CSV/ZIP backup + restore | `backup.py` | stdlib `csv`, `zipfile` |
| Frontend markup | `static/index.html` | HTML5 |
| Styling | `static/css/style.css` | CSS (red + dark gray theme) |
| API client | `static/js/api.js` | thin fetch wrapper |
| UI logic | `static/js/app.js` | vanilla JS |

The server binds to `0.0.0.0:5000` by default so it is reachable on the LAN.
`TETOLATOR_HOST` / `TETOLATOR_PORT` env vars override this.

## Data model

### clients
- `id`, `name` (unique), `notes`, `created_at`

### filaments
- `id`, `name`, `brand`, `material`, `color`, `spool_weight_g`, `price`,
  `notes`, `created_at`
- **price per kg** is computed on demand: `price / (spool_weight_g / 1000)`

### prints
- `id`, `client_id` (FK→clients), `model_name`, `filament_id` (FK→filaments),
  `weight_used_g`, `hours`, `minutes`, `print_date`, `notes`, `created_at`
- Plus a **cost snapshot** written at creation time: `filament_cost`,
  `time_cost`, `markup`, `total_cost`

### settings
- `key` / `value` rows. Keys: `currency`, `cost_per_hour`, `markup_percent`.

### Foreign keys
`prints.client_id` and `prints.filament_id` use `ON DELETE SET NULL`. Deleting
a client or filament never deletes print history; the print keeps existing with
an empty reference.

## Cost calculation

Lives in `models.compute_costs()`. It is called both when saving a print and by
the `POST /api/prints/preview-cost` endpoint (live preview in the form).

```
price_per_kg  = filament.price / (filament.spool_weight_g / 1000)
filament_cost = (weight_used_g / 1000) * price_per_kg
time_cost     = (hours + minutes/60) * settings.cost_per_hour
subtotal      = filament_cost + time_cost
total         = subtotal * (1 + markup_percent/100)
markup        = total - subtotal
```

All four figures are rounded to 2 decimals and **snapshotted** into the print
row, so historical records are stable even if prices or settings change later.

## File-by-file

### app.py
Entry point (`python app.py`). Defines all routes. Serves `static/index.html`
at `/` and static assets under `/css` and `/js`. Everything else is under
`/api`. Each entity has the standard REST verbs. Validation is minimal and
performed in the route handlers (required fields only).

### database.py
Holds the full schema in `SCHEMA` and the helpers `get_connection()` (returns
a row-factory connection with foreign keys on) and `init_db()` (runs the schema
idempotently). The DB file is created at `data/tetolator.db` on first run.

### models.py
All CRUD. One section per entity. Functions take/return plain dicts.
`list_prints()` does a `LEFT JOIN` to attach `client_name` and `filament_name`
for display. `compute_costs()` is the only non-CRUD logic here.

### settings.py
`DEFAULTS` dict + `get_settings()` / `update_settings()`. Numeric keys are
coerced to `float` so the cost math never hits strings.

### backup.py
- `export_zip()` → bytes of a ZIP containing `clients.csv`, `filaments.csv`,
  `prints.csv`, `settings.csv`.
- `export_table(name)` → one table as CSV text.
- `import_zip(bytes)` / `import_table(name, text)` → wipe and replace a table
  (or all tables) from CSV. `settings` is handled separately because it is
  key/value.
- `safe_table_name()` guards the table-name routes against injection.
- Foreign keys are preserved on restore because IDs are exported and re-inserted
  (`INSERT OR REPLACE`). The importer runs inside one transaction per table.

### static/js/api.js
Thin fetch wrapper. Every method returns parsed JSON and throws an `Error` with
the server's `{error}` message on non-2xx responses.

### static/js/app.js
Single-page UI. Holds an in-memory `state` cache of all four datasets, fetched
on boot by `refresh()`. Each tab has a `render*` function plus event binding.
A generic modal (`openModal`) renders form fields as an HTML string and collects
values with `FormData` on submit. Filters are applied client-side in
`filteredPrints()`. The Backup tab uses raw `fetch` with `FormData` (multipart)
because `api.js` only handles JSON.

## REST API summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | health check |
| GET/POST | `/api/clients` | list / create |
| PUT/DELETE | `/api/clients/<id>` | update / delete |
| GET/POST | `/api/filaments` | list / create |
| PUT/DELETE | `/api/filaments/<id>` | update / delete |
| GET/POST | `/api/prints` | list / create |
| PUT/DELETE | `/api/prints/<id>` | update / delete |
| POST | `/api/prints/preview-cost` | compute costs without saving |
| GET/PUT | `/api/settings` | read / update settings |
| GET | `/api/backup/export` | download full ZIP |
| GET | `/api/backup/export/<table>` | download one CSV |
| POST | `/api/backup/import` | restore ZIP |
| POST | `/api/backup/import/<table>` | restore one CSV |

## Running locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

The Flask development server is used intentionally (local network only, small
single-user app). Do not expose it to the public internet.

## Extending the project

- **Add a field to a print:** edit `SCHEMA` in `database.py`, the
  INSERT/UPDATE statements in `models.py`, the modal field template in
  `openPrintModal()` in `app.js`, and the table columns in `renderPrints()`.
  The `prints` CSV export/import picks up new columns automatically because it
  reads the row keys.
- **Add a new entity:** mirror the clients pattern: schema in
  `database.py`, CRUD section in `models.py`, routes in `app.py`, a CSV name in
  `backup.CSV_FILES`, a tab in `index.html`, and a render/bind section in
  `app.js`.
- **Change the cost formula:** only `models.compute_costs()` needs editing.
- **Add authentication / HTTPS:** Flask supports both; keep the `/api` routes
  behind auth and re-serve assets through a proxy if desired.
- **Add statistics / reports:** reuse `list_prints()` and the in-memory
  `state` in the frontend, or add an aggregation endpoint in `app.py`.

## Testing

No automated test suite is included. The project was validated manually by
exercising the full API surface and a backup → wipe → restore round trip.
If you add logic, consider `pytest` with Flask's test client
(`app.app.test_client()`), mirroring the check used during development.
