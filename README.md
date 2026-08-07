# Tetolator

A local-first web app for logging 3D printed parts. Store which client a
print was for, which filament roll was used, the weight, print time and the
automatic cost of each piece.

- **Local only** - runs inside your local network, never exposed to the internet.
- **Automatic cost** - calculated from filament price, print time and your markup.
- **Easy backups** - one click exports everything to CSV files (ZIP), readable in
  any spreadsheet and importable on another machine.

## Requirements

- Python 3.10+ (tested with 3.14)

## Quick start

```bash
# 1. Create a virtual environment (recommended) and install Flask
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Run the server
.venv/bin/python app.py
```

The database and tables are created automatically on first run.

## Opening the app

Open a browser on this computer:

```
http://localhost:5000
```

To use it from **another device on your local network** (phone, tablet,
another PC), open:

```
http://<IP-OF-THIS-MACHINE>:5000
```

Find your machine IP with:

```bash
# Linux
hostname -I

# macOS
ipconfig getifaddr en0

# Windows (PowerShell)
ipconfig
```

## Stopping the server

Press `Ctrl+C` in the terminal where the server is running.

## Setting it up for the first time

1. Open the **Settings** tab and set your **currency**, the **cost per hour**
   (electricity / machine depreciation) and your **markup %**.
2. Open the **Filaments** tab and add the spools you own (name, brand,
   material, spool weight and the price you paid).
3. Open the **Clients** tab and add the clients/projects you print for
   (optional).
4. Open the **Prints** tab and log your first print.

## How the cost is calculated

```
filament cost = weight used (g) ÷ 1000 × filament price per kg
time cost     = (hours + minutes ÷ 60) × cost per hour
subtotal      = filament cost + time cost
total         = subtotal × (1 + markup % ÷ 100)
```

The total is saved as a snapshot when a print is logged, so later changes to
filament prices or settings never rewrite history.

## Backups

In the **Backup** tab:

- **Download full backup (ZIP)** - downloads `tetolator-backup-YYYY-MM-DD.zip`
  containing `clients.csv`, `filaments.csv`, `prints.csv` and `settings.csv`.
  These are plain CSV files you can open in any spreadsheet or text editor.
- Individual CSV exports are also available (prints, clients, filaments).
- **Restore** - upload a ZIP backup or an individual CSV to replace the current
  data. Restoring a backup overwrites the current data.

## Moving to another machine

1. Download a full backup ZIP on the current machine.
2. Copy the ZIP to the new machine (USB drive, shared folder, etc.).
3. Install and start Tetolator there, then use the Backup tab to restore the ZIP.

## Configuration (optional)

| Environment variable | Default | Purpose |
|---|---|---|
| `TETOLATOR_HOST` | `0.0.0.0` | Address to bind. Keep `0.0.0.0` for LAN access. |
| `TETOLATOR_PORT` | `5000` | Port to listen on. |

Example:

```bash
TETOLATOR_PORT=8080 .venv/bin/python app.py
```

## Project layout

```
planner/
  app.py          # Flask routes + REST API + static file serving
  database.py     # SQLite schema and connection helper
  models.py       # CRUD + cost calculation logic
  settings.py     # settings (currency, cost/hour, markup)
  backup.py       # CSV export / import (ZIP and single tables)
  requirements.txt
  data/           # tetolator.db is created here on first run
  static/         # frontend (plain HTML/CSS/JS, no build step)
```

See `LOGGED.md` for a detailed technical walkthrough of how the code works.
