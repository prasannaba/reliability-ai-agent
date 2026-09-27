"""Physics kinematics tools (plain functions; registered in server.py)."""

from __future__ import annotations

import math


def projectile_motion(v0: float, angle_deg: float, g: float = 9.81) -> dict[str, float]:
    """Projectile range / height / flight time for launch speed ``v0`` (m/s).

    ``angle_deg`` is degrees above horizontal, ``g`` gravitational
    acceleration (m/s²). Vacuum, flat ground, no drag.
    """
    if v0 < 0:
        raise ValueError("v0 must be zero or greater")
    if g <= 0:
        raise ValueError("g must be greater than zero")
    theta = math.radians(angle_deg)
    flight_time = 2.0 * v0 * math.sin(theta) / g
    max_range = v0 * v0 * math.sin(2.0 * theta) / g
    max_height = (v0 * math.sin(theta)) ** 2 / (2.0 * g)
    return {
        "range_m": max_range,
        "max_height_m": max_height,
        "flight_time_s": flight_time,
    }


def kinetic_energy(mass_kg: float, velocity_ms: float) -> dict[str, float]:
    """Classical kinetic energy (J) for ``mass_kg`` at ``velocity_ms``."""
    if mass_kg < 0:
        raise ValueError("mass_kg must be zero or greater")
    return {"kinetic_energy_j": 0.5 * mass_kg * velocity_ms * velocity_ms}
