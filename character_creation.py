"""Character creation backend for customizable eras and stat presets.

Provides era presets, templates and simple validation used by the UI.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


ERA_PRESETS: Dict[str, Dict[str, Any]] = {
    "modern": {
        "age_range": (16, 60),
        "stats": {
            "energy": 50,
            "money": 50,
            "skill": 40,
            "reputation": 30,
            "happiness": 60,
            "health": 70,
            "smarts": 55,
            "looks": 50,
        },
    },
    "medieval": {
        "age_range": (12, 45),
        "stats": {
            "energy": 55,
            "money": 10,
            "skill": 45,
            "reputation": 35,
            "happiness": 45,
            "health": 65,
            "smarts": 50,
            "looks": 40,
        },
    },
    "futuristic": {
        "age_range": (18, 80),
        "stats": {
            "energy": 60,
            "money": 70,
            "skill": 60,
            "reputation": 40,
            "happiness": 55,
            "health": 75,
            "smarts": 70,
            "looks": 55,
        },
    },
}


def enumerate_eras() -> list[str]:
    """Return available era keys in a stable order."""
    return list(ERA_PRESETS.keys())


def validate_era(era: str) -> bool:
    return era in ERA_PRESETS


def build_character_template(
    name: str = "Player",
    era: str = "modern",
    age: int | None = None,
    stats_overrides: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    """Build a player template dict suitable for `game_engine.new_game`.

    The returned structure includes `player` with `name`, `location` and `stats`.
    Additional UI stats (happiness, health, smarts, looks) are included to
    support the bar-display shown in the reference screenshot.
    """
    era_key = era if validate_era(era) else "modern"
    preset = ERA_PRESETS[era_key]
    age_min, age_max = preset["age_range"]
    if age is None:
        age = (age_min + age_max) // 2

    base_stats = dict(preset["stats"])  # shallow copy
    if stats_overrides:
        for k, v in stats_overrides.items():
            if isinstance(v, int):
                base_stats[k] = v

    # Map core engine stats (normalize from 0-100 scale to 0-5 scale)
    engine_stats = {
        "energy": max(0, min(5, base_stats.get("energy", 50) // 10)),
        "money": max(0, min(5, base_stats.get("money", 0) // 10)),
        "skill": max(0, min(5, base_stats.get("skill", 0) // 10)),
        "reputation": max(0, min(5, base_stats.get("reputation", 0) // 10)),
    }

    # UI stats for bar display
    ui_stats = {
        "happiness": base_stats.get("happiness", 50),
        "health": base_stats.get("health", 50),
        "smarts": base_stats.get("smarts", 50),
        "looks": base_stats.get("looks", 50),
    }

    pretty_name = name.strip().title() if isinstance(name, str) and name.strip() else "Player"

    return {
        "player": {
            "name": pretty_name,
            "era": era_key,
            "age": age,
            "location": "apartment",
            "stats": engine_stats,
            "ui_stats": ui_stats,
        }
    }
