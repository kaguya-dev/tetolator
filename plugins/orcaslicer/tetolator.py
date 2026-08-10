# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Tetolator"
# description = "Auto-log sliced prints into Tetolator"
# author = "kaguya-dev"
# version = "1.0.0"
# type = "slicing-pipeline"
# ///
"""OrcaSlicer plugin: auto-log sliced prints into Tetolator.

At the ``psGCodePostProcess`` step (G-code export) this capability reads the
stats OrcaSlicer embeds in the exported G-code header:

    ; total filament used [g] = 19.44
    ; estimated printing time (normal mode) = 2h 12m 33s
    ; filament_settings_id = "Sunlu PLA+ @Bambu Lab P1P 0.4 nozzle"

and POSTs a new record to a running Tetolator instance (``POST /api/prints``).
Tetolator computes the final cost from the linked filament profile + settings.

The parsing/network helpers are plain module functions so they can be tested
without OrcaSlicer; importing the ``orca`` module is optional. Any failure is
reported through the ExecutionResult and never blocks or corrupts the export.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

try:
    import orca
except ImportError:  # allow unit testing outside OrcaSlicer
    orca = None

DEFAULT_CONFIG = {
    "base_url": "http://127.0.0.1:5000",
    "default_client_id": "",
}

STATE_FILE = "logged.json"
REQUEST_TIMEOUT = 5  # seconds

# ---------------------------------------------------------------------------
# G-code header parsing
# ---------------------------------------------------------------------------

_TOTAL_G_RE = re.compile(r"^;\s*total filament used \[g\] = ([\d.]+)", re.M)
_FILAMENT_G_RE = re.compile(r"^;\s*filament used \[g\] = ([\d.]+)", re.M)
_TIME_RE = re.compile(
    r"^;\s*estimated printing time \(normal mode\) = (?:(\d+)h\s*)?(\d+)m(?:\s*(\d+)s)?", re.M
)
_TIME_FALLBACK_RE = re.compile(
    r"^;\s*estimated printing time \([^)]*\) = (?:(\d+)h\s*)?(\d+)m(?:\s*(\d+)s)?", re.M
)
_PRESET_RE = re.compile(r'^;\s*filament_settings_id = "([^"]+)"', re.M)
_TYPE_RE = re.compile(r"^;\s*filament_type = ([^\n]+)", re.M)


def parse_gcode_stats(gcode: str) -> dict:
    """Extract weight, time and filament info from an OrcaSlicer G-code header."""
    weight = _match_float(_TOTAL_G_RE.search(gcode))
    if weight is None:
        per_filament = [_match_float(m) for m in _FILAMENT_G_RE.finditer(gcode)]
        weight = round(sum(per_filament), 3) if per_filament else None

    hours = minutes = 0
    time_m = _TIME_RE.search(gcode) or _TIME_FALLBACK_RE.search(gcode)
    if time_m:
        total_minutes = int(time_m.group(1) or 0) * 60 + int(time_m.group(2) or 0)
        if int(time_m.group(3) or 0) >= 30:
            total_minutes += 1
        hours, minutes = divmod(total_minutes, 60)

    preset_m = _PRESET_RE.search(gcode)
    type_m = _TYPE_RE.search(gcode)

    return {
        "weight_used_g": weight,
        "hours": hours,
        "minutes": minutes,
        "filament_preset": preset_m.group(1).strip() if preset_m else None,
        "filament_type": type_m.group(1).strip() if type_m else None,
    }


def _match_float(match) -> float | None:
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def model_name_from_output(output_name) -> str:
    """Derive a model name from OrcaSlicer's output_name (extension stripped)."""
    name = os.path.basename(str(output_name or ""))
    if name.lower().endswith(".gcode"):
        name = name[:-6]
    return name or "untitled"


# ---------------------------------------------------------------------------
# Filament matching
# ---------------------------------------------------------------------------

def match_filament(preset_name: str | None, material: str | None, filaments: list) -> int | None:
    """Best-effort match an Orca filament preset to a Tetolator profile.

    Scoring: exact name match > substring match > material match.
    Returns the matched profile id, or None.
    """
    def norm(value: str | None) -> str:
        return (value or "").strip().lower()

    preset = norm(preset_name)
    mat = norm(material)
    best_id, best_score = None, 0

    for f in filaments or []:
        fname = norm(f.get("name"))
        fbrand = norm(f.get("brand"))
        fmaterial = norm(f.get("material"))
        combined = f"{fname} {fbrand}".strip()

        score = 0
        if preset and fname == preset:
            score = 100
        elif preset and (preset in combined or combined in preset):
            score = 60
        elif preset and fbrand and (preset in fbrand or fbrand in preset):
            score = 50
        if mat and fmaterial == mat:
            score = max(score, 30)
        elif mat and fmaterial and (mat in fmaterial or fmaterial in mat):
            score = max(score, 20)

        if score > best_score:
            best_id, best_score = f.get("id"), score

    return best_id


# ---------------------------------------------------------------------------
# Network (stdlib only)
# ---------------------------------------------------------------------------

def http_json(method: str, url: str, payload: dict | None = None) -> dict:
    """Perform a JSON HTTP request and return the parsed response body."""
    data, headers = None, {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace"))
        except (ValueError, AttributeError):
            detail = {}
        raise RuntimeError(f"Tetolator HTTP {exc.code}: {detail.get('error') or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Cannot reach Tetolator at {url} ({exc})") from exc


def fetch_filaments(base_url: str) -> list:
    return http_json("GET", _api_url(base_url, "filaments")) or []


def post_print(base_url: str, payload: dict) -> dict:
    return http_json("POST", _api_url(base_url, "prints"), payload)


def _api_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/api/" + path


# ---------------------------------------------------------------------------
# Payload + duplicate guard
# ---------------------------------------------------------------------------

def compute_key(model_name: str, print_date: str, weight_g: float) -> str:
    digest = hashlib.sha256()
    digest.update(f"{model_name}|{print_date}|{weight_g}".encode("utf-8"))
    return digest.hexdigest()


def build_payload(stats: dict, model_name: str, config: dict, filament_id=None) -> dict:
    return {
        "model_name": model_name,
        "client_id": str(config.get("default_client_id") or ""),
        "filament_id": str(filament_id or ""),
        "weight_used_g": float(stats.get("weight_used_g") or 0),
        "hours": int(stats.get("hours") or 0),
        "minutes": int(stats.get("minutes") or 0),
        "print_date": date.today().isoformat(),
        "notes": "Auto-logged by OrcaSlicer plugin",
    }


def load_state(plugin_dir: str) -> dict:
    path = Path(plugin_dir) / STATE_FILE
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def plugin_state_dir() -> str:
    """Directory used for the duplicate-guard state file.

    Defaults to the plugin's own folder (inside OrcaSlicer's data dir, so
    writes are audit-allowed). Overridable via env for testing.
    """
    return os.environ.get(
        "TETOLATOR_PLUGIN_STATE_DIR"
    ) or str(Path(__file__).resolve().parent)


def save_state(plugin_dir: str, state: dict) -> None:
    path = Path(plugin_dir) / STATE_FILE
    try:
        path.write_text(json.dumps(state, indent=2), "utf-8")
    except OSError:
        pass  # read-only / audit-blocked: duplicate guard is best-effort


# ---------------------------------------------------------------------------
# OrcaSlicer capability (only defined when running inside the slicer)
# ---------------------------------------------------------------------------

if orca is not None:

    class TetolatorLogger(orca.slicing.SlicingPipelineCapabilityBase):
        def get_name(self):
            return "Tetolator Print Logger"

        def get_default_config(self):
            return dict(DEFAULT_CONFIG)

        def execute(self, ctx):
            if ctx.step != orca.slicing.Step.psGCodePostProcess:
                return orca.ExecutionResult.success()
            if not ctx.gcode_path:
                return orca.ExecutionResult.success("Tetolator: no gcode_path, nothing to do")
            try:
                return self._log_print(ctx)
            except Exception as exc:  # never let a logging failure break the export
                return orca.ExecutionResult.failure(
                    orca.PluginResult.RecoverableError, f"Tetolator: {exc}"
                )

        def _load_config(self) -> dict:
            try:
                cfg = json.loads(self.get_config())
            except (TypeError, ValueError):
                cfg = {}
            merged = dict(DEFAULT_CONFIG)
            merged.update(cfg or {})
            return merged

        def _log_print(self, ctx):
            config = self._load_config()
            base_url = config.get("base_url", DEFAULT_CONFIG["base_url"]).strip().rstrip("/")
            if not base_url:
                return orca.ExecutionResult.failure(
                    orca.PluginResult.RecoverableError,
                    "Tetolator: base_url is empty, configure the plugin first",
                )

            stats = parse_gcode_stats(_read_gcode(ctx.gcode_path))

            preset = stats["filament_preset"]
            if not preset:
                try:
                    preset = ctx.config_value("filament_settings_id")
                except Exception:
                    preset = None
                preset = preset if isinstance(preset, str) else None

            try:
                filaments = fetch_filaments(base_url)
            except RuntimeError:
                filaments = []
            filament_id = match_filament(preset, stats["filament_type"], filaments)

            model_name = model_name_from_output(ctx.output_name)
            weight_g = float(stats.get("weight_used_g") or 0)
            key = compute_key(model_name, date.today().isoformat(), weight_g)

            plugin_dir = plugin_state_dir()
            state = load_state(plugin_dir)
            if key in state:
                return orca.ExecutionResult.success(
                    f"Tetolator: '{model_name}' already logged, skipping"
                )

            payload = build_payload(stats, model_name, config, filament_id)
            created = post_print(base_url, payload)
            new_id = created.get("id")

            state[key] = {"output_name": ctx.output_name or model_name, "id": new_id}
            save_state(plugin_dir, state)

            detail = f"id={new_id}" if new_id else "ok"
            return orca.ExecutionResult.success(
                f"Tetolator: logged '{model_name}' ({detail}, {weight_g}g)"
            )

    def _read_gcode(path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()

    @orca.plugin
    class TetolatorPackage(orca.base):
        def register_capabilities(self):
            orca.register_capability(TetolatorLogger)
