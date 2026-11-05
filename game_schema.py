"""Shared game-state and era schema for Riverton.

This module centralizes default state, normalization, era profiles, and
menu-slot definitions so the engine, UI, and narration layer can share the
same contract.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_PLAYER_STATS = {"energy": 5, "money": 4, "skill": 0, "reputation": 0}
DEFAULT_UI_STATS = {"happiness": 50, "health": 50, "smarts": 50, "looks": 50}


def get_action_budget(age: int | str | None) -> dict[str, int]:
    """Return the annual personal and social action budget for an age.

    The limits deliberately live outside a world pack because they describe the
    core life-sim cadence. Packs decide what an action means; the engine owns
    how many choices a player can make in a year.
    """
    try:
        numeric_age = max(0, int(age if age is not None else 0))
    except (TypeError, ValueError):
        numeric_age = 0
    if numeric_age <= 12:
        return {"personal": 3, "social": 2}
    if numeric_age <= 17:
        return {"personal": 5, "social": 3}
    return {"personal": 7, "social": 4}

ERA_ALIASES = {
    "fantasy": "magic",
    "medieval": "ancient",
    "science fiction": "sci-fi",
    "scifi": "sci-fi",
    "sci fi": "sci-fi",
    "futuristic": "sci-fi",
}


ERA_PROFILES: dict[str, dict[str, Any]] = {
    "modern": {
        "label": "Modern",
        "menu_slots": [
            {"slot": "relations", "label": "Relations", "category": "social"},
            {"slot": "status", "label": "Wellbeing", "category": "status"},
            {"slot": "education", "label": "Education", "category": "education"},
            {"slot": "career", "label": "Career", "category": "career"},
            {"slot": "lifestyle", "label": "Daily Life", "category": "lifestyle"},
            {"slot": "special", "label": "Opportunities", "category": "events"},
        ],
        "dashboard": {
            "brand": "RIVERTON // MODERN LIFE",
            "journal_title": "LIFE LOG",
            "snapshot_title": "LIFE SNAPSHOT",
            "operations_title": "NEXT MOVES",
            "status_stats": [
                {"key": "health", "label": "HEALTH", "color": "#fb7185"},
                {"key": "happiness", "label": "MOOD", "color": "#c084fc"},
                {"key": "smarts", "label": "LEARNING", "color": "#60a5fa"},
                {"key": "looks", "label": "CONFIDENCE", "color": "#fbbf24"},
            ],
            "profile_fields": [
                {"key": "background", "label": "BACKGROUND"},
                {"key": "home", "label": "HOME BASE"},
                {"key": "education", "label": "EDUCATION"},
                {"key": "career", "label": "WORK LIFE"},
                {"key": "social", "label": "SOCIAL CIRCLE"},
                {"key": "standing", "label": "LOCAL STANDING"},
            ],
        },
    },
    "magic": {
        "label": "Magic",
        "menu_slots": [
            {"slot": "relations", "label": "Bonds", "category": "social"},
            {"slot": "status", "label": "Condition", "category": "status"},
            {"slot": "education", "label": "Arcane Study", "category": "education"},
            {"slot": "career", "label": "Calling", "category": "career"},
            {"slot": "lifestyle", "label": "Travel", "category": "lifestyle"},
            {"slot": "special", "label": "Mysteries", "category": "events"},
        ],
        "dashboard": {
            "brand": "RIVERTON // ARCANE LIFE",
            "journal_title": "CHRONICLE",
            "snapshot_title": "ARCANE IDENTITY",
            "operations_title": "OPEN THREADS",
            "status_stats": [
                {"key": "health", "label": "VITALITY", "color": "#fb7185"},
                {"key": "happiness", "label": "COMPOSURE", "color": "#c084fc"},
                {"key": "smarts", "label": "ARCANE STUDY", "color": "#60a5fa"},
                {"key": "looks", "label": "PRESENCE", "color": "#fbbf24"},
            ],
            "profile_fields": [
                {"key": "background", "label": "ORIGIN"},
                {"key": "home", "label": "SANCTUARY"},
                {"key": "education", "label": "STUDY"},
                {"key": "career", "label": "CALLING"},
                {"key": "social", "label": "BONDS"},
                {"key": "standing", "label": "RENOWN"},
            ],
        },
    },
    "sci-fi": {
        "label": "Sci-Fi",
        "menu_slots": [
            {"slot": "relations", "label": "Crew", "category": "social"},
            {"slot": "status", "label": "Readiness", "category": "status"},
            {"slot": "education", "label": "Academy", "category": "education"},
            {"slot": "career", "label": "Assignments", "category": "career"},
            {"slot": "lifestyle", "label": "Station Life", "category": "lifestyle"},
            {"slot": "special", "label": "Signals", "category": "events"},
        ],
        "dashboard": {
            "brand": "RIVERTON // FUTURE LIFE",
            "journal_title": "MISSION LOG",
            "snapshot_title": "CREW FILE",
            "operations_title": "ACTIVE CHANNELS",
            "status_stats": [
                {"key": "health", "label": "HEALTH", "color": "#fb7185"},
                {"key": "happiness", "label": "MORALE", "color": "#c084fc"},
                {"key": "smarts", "label": "SYSTEMS", "color": "#60a5fa"},
                {"key": "looks", "label": "PRESENCE", "color": "#fbbf24"},
            ],
            "profile_fields": [
                {"key": "background", "label": "ORIGIN"},
                {"key": "home", "label": "CURRENT POST"},
                {"key": "education", "label": "TRAINING"},
                {"key": "career", "label": "ASSIGNMENT"},
                {"key": "social", "label": "CREW NETWORK"},
                {"key": "standing", "label": "CLEARANCE"},
            ],
        },
    },
    "ancient": {
        "label": "Ancient",
        "menu_slots": [
            {"slot": "relations", "label": "Kinship", "category": "social"},
            {"slot": "status", "label": "Standing", "category": "status"},
            {"slot": "education", "label": "Training", "category": "education"},
            {"slot": "career", "label": "Service", "category": "career"},
            {"slot": "lifestyle", "label": "Travel", "category": "lifestyle"},
            {"slot": "special", "label": "Omens", "category": "events"},
        ],
        "dashboard": {
            "brand": "RIVERTON // ANCIENT LIFE",
            "journal_title": "HOUSEHOLD RECORD",
            "snapshot_title": "HOUSEHOLD IDENTITY",
            "operations_title": "MATTERS AT HAND",
            "status_stats": [
                {"key": "health", "label": "VIGOR", "color": "#fb7185"},
                {"key": "happiness", "label": "SPIRIT", "color": "#c084fc"},
                {"key": "smarts", "label": "LEARNING", "color": "#60a5fa"},
                {"key": "looks", "label": "PRESENCE", "color": "#fbbf24"},
            ],
            "profile_fields": [
                {"key": "background", "label": "HOUSEHOLD"},
                {"key": "home", "label": "SETTLEMENT"},
                {"key": "education", "label": "TRAINING"},
                {"key": "career", "label": "SERVICE"},
                {"key": "social", "label": "ALLIANCES"},
                {"key": "standing", "label": "RENOWN"},
            ],
        },
    },
}


def normalize_era(era: str | None) -> str:
    if not isinstance(era, str):
        return "modern"
    key = ERA_ALIASES.get(era.strip().lower(), era.strip().lower())
    return key if key in ERA_PROFILES else "modern"


def get_era_profile(era: str | None) -> dict[str, Any]:
    return deepcopy(ERA_PROFILES[normalize_era(era)])


def get_menu_slots(era: str | None) -> list[dict[str, Any]]:
    return deepcopy(get_era_profile(era)["menu_slots"])


def get_dashboard_profile(era: str | None) -> dict[str, Any]:
    """Return era-specific dashboard labels without exposing mutable schema data."""
    return deepcopy(get_era_profile(era)["dashboard"])


def build_default_player(name: str, age: int = 18, era: str = "modern") -> dict[str, Any]:
    return {
        "name": name,
        "age": age,
        "era": normalize_era(era),
        "life_stage": "young adult" if age >= 18 else "child",
        "location": "apartment",
        "stats": deepcopy(DEFAULT_PLAYER_STATS),
        "ui_stats": deepcopy(DEFAULT_UI_STATS),
        "career_tracks": {},
        "education": {"status": "none", "location": None, "level": 0, "grade": "C", "attendance": 0, "school_unlocked": False, "extracurriculars": []},
        "relationship_state": {},
        "mutation_state": {},
    }


def build_default_state(name: str, origin: dict[str, Any], era: str = "modern") -> dict[str, Any]:
    player = build_default_player(name, era=era)
    return {
        "player": player,
        "origin": deepcopy(origin),
        "year": 1,
        "season_index": 0,
        "actions_remaining": 3,
        "npcs": [],
        "flags": {},
        "memories": [],
        "encounters": [],
        "active_random_event": None,
        "random_seen_this_season": False,
        "seen_random_events": [],
        "completed": False,
        "completed_milestones": [],
        "milestone_events_pending": [],
        "dynamic_locations": {},
        "dynamic_npcs": [],
        "starting_scenario": "",
        "starting_map": {},
        "game_folder": "",
        "education": {"status": "none", "location": None, "forced": False, "school_unlocked": False, "grade": "C", "attendance": 0, "extracurriculars": []},
        "career_tracks": {},
        "parents": {"strictness": 0.5, "support": 0.5, "name": "Parents"},
        "world": {"era": normalize_era(era), "phase": "baseline", "unlocks": {}},
    }


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Fill in missing nested state keys without mutating the input."""
    normalized = deepcopy(state)
    player = normalized.setdefault("player", {})
    player.setdefault("name", "Player")
    player.setdefault("age", 18)
    player.setdefault("era", "modern")
    player.setdefault("life_stage", "young adult" if player.get("age", 18) >= 18 else "child")
    player.setdefault("location", "apartment")
    player.setdefault("stats", deepcopy(DEFAULT_PLAYER_STATS))
    player.setdefault("ui_stats", deepcopy(DEFAULT_UI_STATS))
    player.setdefault("career_tracks", {})
    player.setdefault("education", {"status": "none", "location": None, "level": 0, "grade": "C", "attendance": 0, "school_unlocked": False, "extracurriculars": []})
    player.setdefault("relationship_state", {})
    player.setdefault("mutation_state", {})

    normalized.setdefault("origin", {})
    normalized.setdefault("year", 1)
    normalized.setdefault("season_index", 0)
    normalized.setdefault("actions_remaining", 3)
    normalized.setdefault("npcs", [])
    normalized.setdefault("flags", {})
    normalized.setdefault("memories", [])
    normalized.setdefault("encounters", [])
    normalized.setdefault("active_random_event", None)
    normalized.setdefault("random_seen_this_season", False)
    normalized.setdefault("seen_random_events", [])
    normalized.setdefault("completed", False)
    normalized.setdefault("completed_milestones", [])
    normalized.setdefault("milestone_events_pending", [])
    normalized.setdefault("dynamic_locations", {})
    normalized.setdefault("dynamic_npcs", [])
    normalized.setdefault("starting_scenario", "")
    normalized.setdefault("starting_map", {})
    normalized.setdefault("game_folder", "")
    normalized.setdefault("education", {"status": "none", "location": None, "forced": False, "school_unlocked": False, "grade": "C", "attendance": 0, "extracurriculars": []})
    normalized.setdefault("career_tracks", {})
    normalized.setdefault("parents", {"strictness": 0.5, "support": 0.5, "name": "Parents"})
    normalized.setdefault("world", {"era": normalize_era(player.get("era")), "phase": "baseline", "unlocks": {}})
    normalized["world"].setdefault("era", normalize_era(player.get("era")))
    normalized["world"].setdefault("phase", "baseline")
    normalized["world"].setdefault("unlocks", {})
    return normalized
