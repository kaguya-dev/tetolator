# Tetolator plugin for OrcaSlicer

Auto-logs sliced prints into Tetolator. After each slice/export, the plugin
reads the stats OrcaSlicer embeds in the G-code header and POSTs a new record
to Tetolator's `POST /api/prints` endpoint. Tetolator computes the final cost.

- Works with OrcaSlicer **2.4.x** (native Python plugin system).
- Requires a **running Tetolator** instance reachable from this machine.
- Uses **estimated** print time from the slicer (slice/export-time logging).

## Install

1. Make sure the plugin file is in place:

   ```bash
   mkdir -p ~/.config/OrcaSlicer/orca_plugins/tetolator
   cp tetolator.py ~/.config/OrcaSlicer/orca_plugins/tetolator/
   ```

2. Restart OrcaSlicer (or reopen the Plugins window).
3. Open **Help -> Plugins**, find **Tetolator**, and enable the
   **Tetolator Print Logger** capability.
4. In the **Config** tab (JSON editor) set:
   - `base_url` - where Tetolator runs, e.g. `http://127.0.0.1:5000`
     (use your machine's LAN IP if Tetolator runs on another computer).
   - `default_client_id` - the client/project every auto-logged print is
     linked to (find the id in Tetolator's URL/API, or leave `""`).

   Example config:
   ```json
   {
     "base_url": "http://127.0.0.1:5000",
     "default_client_id": "1"
   }
   ```

5. Slice/export a model. A new print appears in Tetolator's **Prints** tab.

## How it maps data

| OrcaSlicer source | Tetolator field |
|---|---|
| `; filament_settings_id = "..."` | matched to a filament profile by name |
| `; total filament used [g] = 19.44` | `weight_used_g` |
| `; estimated printing time (normal mode) = 2h 12m 33s` | `hours`, `minutes` |
| output file name (e.g. `benchy.gcode`) | `model_name` |
| plugin config | `client_id` |
| today's date | `print_date` |

Cost is computed by Tetolator from the linked filament price + settings, so
nothing cost-related lives in the plugin.

## Filament matching

Best-effort, ranked: exact name match > substring match > material match
(`filament_type`). If nothing matches, the print is logged with no filament so
you can link it later in the Tetolator UI.

## Duplicate protection

Re-exporting the same slice does not create a second record. The plugin keeps a
small `logged.json` (hash of model + date + weight) in its own plugin folder
and skips already-logged exports. Delete that file to force a re-log.

## Troubleshooting

- **Nothing appears after slicing**: Tetolator must be running and
  `base_url` reachable. Open the Plugins window and check the last run result,
  or watch `~/.config/OrcaSlicer/log/python_*.log`.
- **"Cannot reach Tetolator"**: wrong `base_url`, or the server is off.
- **Print logged without a filament**: no profile matched - add/fix the name
  in Tetolator's Filaments tab (or edit the record afterwards).
- The plugin never modifies or blocks the G-code export; failures only surface
  a warning in the Plugins dialog.

## Development & testing

- `tetolator.py` imports `orca` optionally, so all parsing/network helpers can
  be tested outside OrcaSlicer.
- Parser tests: `python3 plugins/orcaslicer/tests/test_parser.py`
- Full harness (stubbed `orca`, live Tetolator):
  `python3 plugins/orcaslicer/tests/test_plugin_live.py http://127.0.0.1:5000`

## Known limitations (v1)

- Uses the slicer's **estimated** time, not actual print time (a real
  completion hook needs the immature Printer Agent API - a future v2).
- Single-extruder prints only.
- Config is edited via the built-in JSON editor (no custom HTML UI yet).
