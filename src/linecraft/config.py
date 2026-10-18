"""Load Linecraft config. Defaults pull the configured book and research with Grok."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "sporty",
    "providers": ["sporty", "1xbet"],
    "window": {"start": "00:00", "end": "09:00", "timezone": "Africa/Lagos"},
    "sports": ["Football", "Basketball", "Ice Hockey", "American Football", "Tennis"],
    "pages": {"Football": 2, "Basketball": 1, "Ice Hockey": 1, "American Football": 1, "Tennis": 1},
    "markets": {
        "Football": ["18", "1"],
        "Basketball": ["225", "219"],
        "Ice Hockey": ["406", "18"],
        "American Football": ["225", "219"],
        "Tennis": ["186"],
    },
    "odds": {"min": 1.4, "max": 50.0},
    "hold_max": 0.12,
    "max_legs": 12,
    "batch_size": 2,
    "max_board": 24,
    "grok": {
        "enabled": True,
        "model": "grok-4.7",
        "timeout_seconds": 240,
        "require_search": True,
    },
    "book": {"enabled": True, "mode": "share", "stake": False},
    "output_dir": "out",
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | None = None) -> dict[str, Any]:
    """Read JSON config. Missing file falls back to the built-in defaults."""
    chosen = path or os.environ.get("LINECRAFT_CONFIG") or ""
    if not chosen:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    file_path = Path(chosen)
    if not file_path.is_absolute():
        file_path = ROOT / file_path
    if not file_path.exists():
        raise FileNotFoundError(f"config not found: {file_path}")
    payload = json.loads(file_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("config must be a JSON object")
    config = _deep_merge(DEFAULT_CONFIG, payload)
    if config.get("book", {}).get("stake") is not False:
        raise ValueError("book.stake must be false; Linecraft books share codes only")
    if config.get("book", {}).get("mode") not in (None, "share"):
        raise ValueError("book.mode must be share")
    return config
