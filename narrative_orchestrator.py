"""Compact context builder for Riverton's local narrative model.

The rules engine remains authoritative. This module only selects and
condenses game data into a small prompt-friendly payload for narration and
branch suggestion.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from game_schema import get_menu_slots, normalize_era


def _trim_text(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _compact_memory_entries(memories: list[Any], limit: int = 4) -> list[str]:
    items: list[str] = []
    for mem in memories[-limit:]:
        if isinstance(mem, str):
            items.append(_trim_text(mem, 180))
        elif isinstance(mem, dict):
            text = mem.get("text", "")
            if isinstance(text, str) and text.strip():
                items.append(_trim_text(text, 180))
    return items[-limit:]


def build_narration_context(state: dict[str, Any], *, max_npcs: int = 4, max_memories: int = 4) -> dict[str, Any]:
    """Return a compact model-facing snapshot of the current game state."""
    player = deepcopy(state.get("player", {}))
    npcs = []
    current_location = player.get("location")
    for npc in state.get("npcs", []):
        if not isinstance(npc, dict):
            continue
        if current_location and npc.get("location") != current_location:
            continue
        npcs.append(
            {
                "id": npc.get("id"),
                "name": npc.get("name"),
                "role": npc.get("role"),
                "location": npc.get("location"),
                "affinity": npc.get("affinity", 0),
                "trust": npc.get("trust", 0),
            }
        )
        if len(npcs) >= max_npcs:
            break

    stats = dict(player.get("stats", {}))
    ui_stats = dict(player.get("ui_stats", {}))
    memories = _compact_memory_entries(state.get("memories", []), limit=max_memories)
    flags = dict(state.get("flags", {}))

    return {
        "year": state.get("year", 1),
        "season": state.get("season", ""),
        "actions_remaining": state.get("actions_remaining", 0),
        "completed": bool(state.get("completed", False)),
        "active_event": _trim_text((state.get("active_random_event") or {}).get("title", ""), 80) if state.get("active_random_event") else None,
        "player": {
            "name": player.get("name", "Player"),
            "age": player.get("age"),
            "location": current_location,
            "origin": state.get("origin", {}).get("name", ""),
            "stats": stats,
            "ui_stats": ui_stats,
        },
        "relationships": npcs,
        "flags": flags,
        "recent_memories": memories,
        "story_beats": {
            "season_summary": _trim_text(state.get("season_summary", ""), 240) if isinstance(state.get("season_summary"), str) else "",
            "starting_scenario": _trim_text(state.get("starting_scenario", ""), 240) if isinstance(state.get("starting_scenario"), str) else "",
        },
        "menu_slots": get_menu_slots(normalize_era(player.get("era", state.get("world", {}).get("era", "modern")))),
        "world": deepcopy(state.get("world", {"era": normalize_era(player.get("era", "modern"))})),
    }


def build_narration_prompt_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return the compact payload used by the local model prompt."""
    return build_narration_context(state)


def build_world_event_context(
    state: dict[str, Any], title: str, outcome: str, event_type: str = "encounter"
) -> dict[str, Any]:
    """Build a small, rules-safe payload for one short world-event narration."""
    player = state.get("player", {}) if isinstance(state, dict) else {}
    profile = player.get("naruto", {}) if isinstance(player, dict) else {}
    world = state.get("world", {}) if isinstance(state, dict) else {}
    return {
        "event_type": _trim_text(str(event_type), 24),
        "title": _trim_text(str(title), 80),
        "outcome": _trim_text(str(outcome), 220),
        "age": player.get("age", 0),
        "character": _trim_text(str(player.get("name", "Shinobi")), 32),
        "rank": _trim_text(str(world.get("rank", "Academy Student")), 24),
        "location": _trim_text(str(player.get("location", "home")).replace("_", " "), 40),
        "chakra_nature": _trim_text(str(profile.get("chakra_nature", {}).get("name", "Unawakened")), 20),
        "recent_memories": _compact_memory_entries(state.get("memories", []), limit=2),
    }
