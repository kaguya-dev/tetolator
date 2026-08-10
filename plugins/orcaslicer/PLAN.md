# OrcaSlicer Plugin - Implementation Plan (Future Work)

This document is a plan for adding an **OrcaSlicer plugin** that automatically
logs sliced prints into Tetolator. It is written to be picked up later by a
developer (human or AI) and executed as-is. Nothing here has been implemented
yet.

Status: **Implemented** - see `README.md` in this directory and the root
`README.md` / `LOGGED.md` for the finished plugin, tests, and install steps.
The plan below is kept for historical reference.

---

## Goal

When the user slices/exports a model in OrcaSlicer 2.x, the plugin extracts
print statistics from the generated G-code and POSTs a new record into
Tetolator's existing REST API (`POST /api/prints`). Tetolator already computes
the cost from the selected filament profile + settings, so **no changes to the
Tetolator backend are required**.

## Decisions already confirmed

| Question | Decision |
|---|---|
| When to log | On **slice/export** (`psGCodePostProcess` step) |
| Client assignment | **Fixed default client**, chosen in the plugin config |
| Filament matching | **Auto substring match** on filament name |
| Code location | Same repo: `plugins/orcaslicer/` |
| Network | stdlib `urllib.request`, zero dependencies |
| OrcaSlicer target | 2.4.x (installed at `/usr/bin/orca-slicer`, data dir `~/.config/OrcaSlicer`) |

## Effort estimate

Roughly **4-6 hours** including a live end-to-end test. Moderate - the plugin
API is new and sparsely documented, so expect a debug loop using the Python
plugin log.

---

## Architecture

```
OrcaSlicer slicing pipeline (psGCodePostProcess)
        │  ctx.gcode_path, ctx.output_name
        ▼
tetolator.py
  1. parse_gcode_stats(gcode_path)   -> weight_g, hours, minutes, filament_preset
  2. match_filament(filament_preset) -> GET /api/filaments, substring match
  3. build payload                   -> model_name, client_id, filament_id,
                                       weight_used_g, hours, minutes, print_date
  4. duplicate guard                 -> hash log in plugin data_dir
  5. POST /api/prints                -> urllib.request
```

## File layout

```
plugins/orcaslicer/
  tetolator.py    # the plugin (single .py file, PEP 723 metadata)
  PLAN.md         # this document
```

Install destination (after implementation):

```
~/.config/OrcaSlicer/orca_plugins/tetolator/tetolator.py
```

## Plugin skeleton

### 1. PEP 723 metadata block

```python
# /// script
# [tool.orcaslicer.plugin]
# name = "Tetolator"
# description = "Auto-log sliced prints into Tetolator"
# author = "kaguya-dev"
# version = "1.0.0"
# requires-python = ">=3.8"
# dependencies = []
# ///
```

### 2. Capability registration

- One package class marked with `@orca.plugin`, overriding
  `register_capabilities()`.
- Register exactly one capability of type
  `orca.slicing.SlicingPipelineCapabilityBase`.
- Required methods: `get_name()` and `execute(self, ctx)`.

### 3. `execute(ctx)` behavior

1. Bail early unless `ctx.step == orca.slicing.Step.psGCodePostProcess`
   (return `orca.ExecutionResult.success()` otherwise).
2. Read plugin config via `get_config()` (JSON string):
   - `base_url` (default `http://127.0.0.1:5000`)
   - `default_client_id` (empty = log without client)
3. Parse `ctx.gcode_path` (see data mapping below).
4. Match filament profile against `GET {base_url}/api/filaments`.
5. Run duplicate guard (see below).
6. `POST {base_url}/api/prints` with the payload.
7. Return `orca.ExecutionResult.success(...)` on success, or a
   `failure(...)` result carrying the error message on parse/network errors.
   Never modify or corrupt the G-code file.
8. The capability runs on the slicing worker thread - **do not** call
   `orca.host.ui.*` (deadlock risk). Report via log / ExecutionResult only.

### 4. Config UI (optional but nice)

- `has_config_ui() -> True`, `get_config_ui()` returns a self-contained HTML
  string with:
  - a text input for `base_url`
  - a `<select>` of clients populated from `GET {base_url}/api/clients`
- `get_default_config()` returns
  `{"base_url": "http://127.0.0.1:5000", "default_client_id": ""}`
- Persist with `save_config(json.dumps(...))`.

---

## Data mapping

Source is the exported G-code header produced by OrcaSlicer:

| G-code line / context | Parse | Tetolator field |
|---|---|---|
| `; filament_settings_id = "Sunlu PLA @Bambu Lab P1P 0.4 nozzle"` | preset name | matched to `filaments.name` (case-insensitive substring) |
| `; total filament used [g] = 20.66` | float | `weight_used_g` |
| `; estimated printing time (normal mode) = 1h 23m 45s` | hours + minutes | `hours`, `minutes` |
| `ctx.output_name` | strip `.gcode` | `model_name` |
| plugin config | — | `client_id` |
| today's date (`YYYY-MM-DD`) | — | `print_date` |
| Tetolator computes | — | `filament_cost`, `time_cost`, `markup`, `total_cost` |

### Parsing rules

- **Weight:** prefer `; total filament used [g] = ...`; fall back to summing
  all `; filament used [g] = ...` lines. Missing value -> log without weight
  (or skip, see "edge cases").
- **Time:** regex for `(\d+)h\s+(\d+)m(?: \d+s)?`. Also handle a pure
  seconds form if present. Missing -> `0h 0m`.
- **Filament preset:** parse `filament_settings_id`. If the line is absent,
  fall back to `; filament_type = PLA` and match on material only.
- **Model name:** `ctx.output_name` with extension removed. Do NOT try to strip
  the trailing quality/filament suffixes (e.g. `_0.2mm_PLA`) - keep it simple.

### Filament matching algorithm

1. `GET {base_url}/api/filaments`.
2. Score each profile: exact name match (case-insensitive) > substring match >
   material match on `filament_type`.
3. Prefer the highest score; on ties prefer the first alphabetically.
4. No match -> send payload with `filament_id: null` (Tetolator allows it);
   the user can link the filament later in the Prints screen.

---

## Duplicate guard

Exporting the same slice repeatedly must not create duplicate records.

- After parsing, compute `hash(model_name + print_date + weight_used_g)`.
- Maintain a JSON file in the plugin data dir
  (`data_dir()/orca_plugins/tetolator/logged.json`) mapping `hash -> gcode file
  identity` (or timestamp).
- If the hash already exists for the same G-code output, skip the POST.
- File writes are allowed under `data_dir()` per the Plugin Audit Hook.

## Error handling / edge cases

- Network down (Tetolator not running): log a clear message, return a
  `failure` ExecutionResult. Never crash the slicer.
- Unparseable G-code header: skip silently with a log line; don't block export.
- Multi-extruder prints: only support single-extruder in v1; use
  `filament_settings_id` of the active preset. Document as a known limitation.
- `--slice` CLI mode: same code path, no special handling needed.

---

## Config reference

| Config key | Type | Default | Purpose |
|---|---|---|---|
| `base_url` | string | `http://127.0.0.1:5000` | Tetolator server address (LAN IP if remote) |
| `default_client_id` | int/string | `""` | Client linked to every auto-logged print |

Environment: Tetolator must be running and reachable from the machine running
OrcaSlicer. No auth exists in Tetolator v1; fine for LAN-only use.

---

## Testing checklist

### 1. Parser unit test (no OrcaSlicer needed)
- Stub an `orca` module (empty module with the used symbols) so the plugin can
  be imported outside the slicer, or extract the parser functions so they are
  importable without `orca`.
- Feed a sample G-code header (include the stat lines above) and assert the
  extracted `weight_used_g`, `hours`, `minutes`, `filament_preset`.

### 2. HTTP integration
- Start Tetolator (`python app.py`), create a client + a matching filament
  profile via the UI/API.
- Send the exact payload the plugin would send to `POST /api/prints`.
- Assert the record appears and `total_cost` is calculated correctly.

### 3. Live end-to-end in OrcaSlicer
- Copy plugin to `~/.config/OrcaSlicer/orca_plugins/tetolator/tetolator.py`.
- Open OrcaSlicer -> Plugins window -> confirm the plugin + capability appear.
- Configure `base_url` and default client in the Config tab.
- Slice/export a real model.
- Watch `~/.config/OrcaSlicer/log/python_*.log` during development.
- Verify the record in Tetolator's Prints tab and via `GET /api/prints`.

---

## Documentation updates (after implementation)

1. `plugins/orcaslicer/README.md` - install/enable steps for OrcaSlicer 2.4.x,
   config reference, troubleshooting (log location, Tetolator must be running).
2. `README.md` (root) - short section linking to the plugin.
3. `LOGGED.md` - add a section documenting the plugin's architecture following
   the same "future devs/AI" style.

## Known limitations (v1)

- Uses the slicer's **estimated** time, not actual print time. Real completion
  time would require the immature `PrinterAgentBase` API - a future v2 item.
- Filament match is best-effort substring; unmatched prints log without a
  filament and are fixable later in the UI.
- Single-extruder only.

## Reference links

- OrcaSlicer plugin development wiki:
  https://github.com/OrcaSlicer/OrcaSlicer/wiki/plugin_development
- Slicing pipeline API:
  https://www.orcaslicer.com/wiki/developer_reference/plugin_development/api_reference/slicing.html
- Printer agent API (future v2):
  https://www.orcaslicer.com/wiki/developer_reference/plugin_development/api_reference/printer_agent.html
- Plugin audit hook (filesystem write rules):
  https://github.com/OrcaSlicer/OrcaSlicer/wiki/plugin_audit_hook
