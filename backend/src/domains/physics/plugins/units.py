"""Unit-conversion plugin for the physics MCP server."""

from __future__ import annotations

from typing import Any


def register(mcp: Any) -> None:
    @mcp.tool()
    def convert_units(value: float, from_unit: str, to_unit: str) -> dict[str, float | str]:
        """Convert between supported length/energy units (m, km, ft, J, kJ, eV)."""
        length = {"m": 1.0, "km": 1000.0, "ft": 0.3048}
        energy = {"j": 1.0, "kj": 1000.0, "ev": 1.602176634e-19}
        table: dict[str, float] | None = None
        if from_unit in length and to_unit in length:
            table = length
        elif from_unit.lower() in energy and to_unit.lower() in energy:
            table = {key.lower(): val for key, val in energy.items()}
            from_unit, to_unit = from_unit.lower(), to_unit.lower()
        if table is None:
            raise ValueError(f"unsupported conversion: {from_unit} -> {to_unit}")
        return {
            "value": value * table[from_unit] / table[to_unit],
            "from": from_unit,
            "to": to_unit,
        }
