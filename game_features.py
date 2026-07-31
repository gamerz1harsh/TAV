"""Additional gameplay systems for Riverton.

These features extend the base game without replacing the rules engine.
The first iteration focuses on season summaries, memory filtering, and a
lightweight relationship story system.
"""
from __future__ import annotations

from typing import Any


def build_season_summary(previous_state: dict[str, Any], current_state: dict[str, Any], focus: str) -> str:
    prev_stats = previous_state.get("player", {}).get("stats", {})
    curr_stats = current_state.get("player", {}).get("stats", {})
    prev_npcs = {npc.get("id"): npc for npc in previous_state.get("npcs", []) if npc.get("id")}
    curr_npcs = {npc.get("id"): npc for npc in current_state.get("npcs", []) if npc.get("id")}

    changes = []
    for stat in ("energy", "money", "skill", "reputation"):
        before = prev_stats.get(stat, 0)
        after = curr_stats.get(stat, 0)
        if after != before:
            changes.append(f"{stat} {before}->{after}")

    npc_changes = []
    for npc_id in sorted(set(prev_npcs) | set(curr_npcs)):
        prev_npc = prev_npcs.get(npc_id, {})
        curr_npc = curr_npcs.get(npc_id, {})
        if curr_npc.get("trust", 0) != prev_npc.get("trust", 0) or curr_npc.get("affinity", 0) != prev_npc.get("affinity", 0):
            npc_changes.append(f"{curr_npc.get('name', npc_id)} trust/affinity changed")

    summary_parts = [f"This season you leaned into {focus.lower()}."]
    if changes:
        summary_parts.append("Key shifts: " + ", ".join(changes) + ".")
    if npc_changes:
        summary_parts.append("Relationship signals: " + "; ".join(npc_changes) + ".")
    if not npc_changes and not changes:
        summary_parts.append("The season was quiet and the story stayed mostly still.")
    return " ".join(summary_parts)


def filter_memories(memories: list[str], mode: str = "all") -> list[str]:
    if mode == "recent":
        return memories[-6:]
    if mode == "important":
        return [memory for memory in memories if any(keyword in memory.lower() for keyword in ("trust", "focus", "shift", "campaign", "cafe", "mentor"))]
    return list(memories)


def build_character_sheet_data(state: dict[str, Any]) -> dict[str, Any]:
    player = state.get("player", {})
    stats = player.get("stats", {})
    ui_stats = player.get("ui_stats", {})
    relationships = []
    for npc in state.get("npcs", []):
        relationships.append({
            "id": npc.get("id"),
            "name": npc.get("name", npc.get("id", "Unknown")),
            "role": npc.get("role", ""),
            "trust": npc.get("trust", 0),
            "affinity": npc.get("affinity", 0),
        })
    # Present the player name in title case for readability in the UI
    raw_name = player.get("name", "Unknown")
    pretty_name = raw_name.strip().title() if isinstance(raw_name, str) else "Unknown"

    return {
        "name": pretty_name,
        "location": player.get("location", "apartment"),
        "stats": {
            "energy": stats.get("energy", 0),
            "money": stats.get("money", 0),
            "skill": stats.get("skill", 0),
            "reputation": stats.get("reputation", 0),
        },
        "ui_stats": {
            "happiness": ui_stats.get("happiness", 50),
            "health": ui_stats.get("health", 50),
            "smarts": ui_stats.get("smarts", 50),
            "looks": ui_stats.get("looks", 50),
        },
        "relationships": sorted(relationships, key=lambda item: (item["trust"] + item["affinity"]), reverse=True),
        "paths": state.get("opportunities", []),
        "season_summary": state.get("season_summary") or "No seasonal summary yet.",
        "starting_scenario": state.get("starting_scenario", ""),
        "starting_map": state.get("starting_map", {}),
        "dynamic_locations": state.get("dynamic_locations", {}),
        "all_locations": state.get("all_locations", {}),
    }


def format_map_for_display(map_data: dict[str, Any]) -> str:
    """Format map data into a readable string for the UI."""
    if not map_data:
        return "No map data available."
    center = map_data.get("center", "Unknown")
    locations = map_data.get("locations", {})
    lines = [f"📍 {center}"]
    if isinstance(locations, dict):
        for loc_id, loc_desc in locations.items():
            lines.append(f"  • {loc_desc}")
    elif isinstance(locations, list):
        for loc in locations:
            if isinstance(loc, str):
                lines.append(f"  • {loc.replace('_', ' ').title()}")
            elif isinstance(loc, dict):
                lines.append(f"  • {loc.get('description', loc.get('id', 'Unknown'))}")
    return "\n".join(lines)


def format_ui_stats_for_display(ui_stats: dict[str, int]) -> list[dict[str, Any]]:
    """Format UI stats into a list of dicts with name, value, and bar percentage."""
    stat_configs = [
        ("happiness", "😊 Happiness"),
        ("health", "❤️ Health"),
        ("smarts", "🧠 Smarts"),
        ("looks", "✨ Looks"),
    ]
    result = []
    for key, label in stat_configs:
        value = ui_stats.get(key, 50)
        # Clamp to 0-100
        value = max(0, min(100, value))
        result.append({
            "key": key,
            "label": label,
            "value": value,
            "percentage": value / 100.0,
        })
    return result
