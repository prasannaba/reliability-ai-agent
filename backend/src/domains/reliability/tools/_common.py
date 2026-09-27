"""Shared helpers for reliability MCP tools."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[4]
STATIC_DIR = BACKEND_DIR / "static"

#: Serialise matplotlib output — one plot at a time.
PLOT_LOCK = Lock()


def json_safe(value: Any) -> Any:
    """Convert NumPy, tuples, and path values into MCP-safe JSON values."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
