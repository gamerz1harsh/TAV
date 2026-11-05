"""World Mutation System for Riverton V1.

Large actions alter the world beyond the player. Tracks global state,
faction power, unlocks, rumors, and world events. When a world-changing
event happens, the game updates world state, unlocks menu cards, changes
future encounters, and affects NPC reactions.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_WORLD_STATE: dict[str, Any] = {
    "era": "modern",
    "phase": "baseline",  # baseline, changed, transformed, collapsed
    "global_flags": {},
    "factions": {
        "corporate": {"power": 50, "trust": 0},
        "community": {"power": 50, "trust": 0},
        "government": {"power": 50, "trust": 0},
        "criminal": {"power": 30, "trust": 0},
    },
    "unlocks": {},
    "menu_swaps": {},
    "rumors": [],
    "active_crises": [],
    "world_events": [],
    "history": [],
}


def get_world_state(state: dict[str, Any]) -> dict[str, Any]:
    """Get the world state from the game state, ensuring defaults exist."""
    world = state.setdefault("world", {})
    for key, default in DEFAULT_WORLD_STATE.items():
        if key not in world:
            world[key] = deepcopy(default)
    return world


def apply_world_effects(state: dict[str, Any], effects: dict[str, Any]) -> dict[str, Any]:
    """Apply world-level effects to the game state.

    Args:
        state: The game state.
        effects: World effects dict with keys:
            - world_flags: dict of global flags to set
            - faction_changes: dict of faction_id -> power delta
            - unlocks: list of system IDs to unlock
            - menu_swaps: dict of slot_id -> new slot definition
            - rumors: list of rumor strings to add
            - phase: new world phase

    Returns:
        The updated world state.
    """
    world = get_world_state(state)

    # World flags
    world_flags = effects.get("world_flags", {})
    if world_flags:
        world["global_flags"].update(world_flags)

    # Faction changes
    faction_changes = effects.get("faction_changes", {})
    for faction_id, delta in faction_changes.items():
        faction = world["factions"].setdefault(faction_id, {"power": 50, "trust": 0})
        faction["power"] = max(0, min(100, faction.get("power", 50) + delta))

    # Unlocks
    unlocks = effects.get("unlocks", [])
    for unlock in unlocks:
        world["unlocks"][unlock] = True

    # Menu swaps
    menu_swaps = effects.get("menu_swaps", {})
    if menu_swaps:
        world["menu_swaps"].update(menu_swaps)

    # Rumors
    rumors = effects.get("rumors", [])
    if rumors:
        world["rumors"].extend(rumors)
        world["rumors"] = world["rumors"][-20:]  # Keep last 20

    # Phase change
    if "phase" in effects:
        world["phase"] = effects["phase"]

    # Record history
    if effects.get("event_id"):
        world["history"].append({
            "event_id": effects["event_id"],
            "phase": world["phase"],
            "unlocks": list(unlocks),
        })

    return world


def get_menu_slots_with_swaps(state: dict[str, Any], base_slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply menu swaps to the base era menu slots.

    Args:
        state: The game state.
        base_slots: The base era menu slots.

    Returns:
        The menu slots with any world-state swaps applied.
    """
    world = get_world_state(state)
    swaps = world.get("menu_swaps", {})
    if not swaps:
        return base_slots

    result = []
    for slot in base_slots:
        slot_id = slot.get("slot")
        if slot_id in swaps:
            swap = swaps[slot_id]
            merged = dict(slot)
            merged.update(swap)
            result.append(merged)
        else:
            result.append(slot)
    return result


def get_world_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Get a summary of the world state for UI display."""
    world = get_world_state(state)
    return {
        "era": world.get("era", "modern"),
        "phase": world.get("phase", "baseline"),
        "factions": world.get("factions", {}),
        "unlocks": list(world.get("unlocks", {}).keys()),
        "rumors": world.get("rumors", [])[-5:],
        "active_crises": world.get("active_crises", []),
        "history_count": len(world.get("history", [])),
    }


def check_world_phase(state: dict[str, Any]) -> str:
    """Determine the current world phase based on global state.

    Phases:
    - baseline: Normal world
    - changed: Significant world changes have occurred
    - transformed: Major transformation (e.g., gene era, magic breakthrough)
    - collapsed: World has collapsed or fundamentally changed
    """
    world = get_world_state(state)
    global_flags = world.get("global_flags", {})
    unlocks = world.get("unlocks", {})

    # Check for collapse conditions
    if global_flags.get("world_collapsed") or global_flags.get("apocalypse"):
        return "collapsed"

    # Check for transformation conditions
    if global_flags.get("gene_era") or global_flags.get("magic_breakthrough") or global_flags.get("ai_singularity"):
        return "transformed"

    # Check for significant changes
    if len(unlocks) >= 3 or len(global_flags) >= 5:
        return "changed"

    return "baseline"


def get_era_shift_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Get events that could trigger an era shift based on current state.

    Returns a list of potential era-shift event definitions.
    """
    world = get_world_state(state)
    global_flags = world.get("global_flags", {})
    unlocks = world.get("unlocks", {})

    events = []

    # Gene warrior path
    if global_flags.get("gene_research") and not unlocks.get("gene_warrior_path"):
        events.append({
            "id": "gene_breakthrough",
            "title": "The Gene Breakthrough",
            "framework": "world_event",
            "text": "Your research has reached a critical point. The world will never be the same.",
            "choices": [
                {"id": "share", "label": "Share the discovery", "effects": {"reputation": 5, "world_flags": {"gene_era": True}, "unlocks": ["gene_warrior_path"], "faction_changes": {"community": 10}}},
                {"id": "sell", "label": "Sell to a corporation", "effects": {"money": 10, "world_flags": {"gene_era": True}, "unlocks": ["gene_warrior_path"], "faction_changes": {"corporate": 15}}},
                {"id": "hide", "label": "Keep it secret", "effects": {"flags": {"secret_breakthrough": True}}},
            ],
        })

    # Magic breakthrough
    if global_flags.get("arcane_research") and not unlocks.get("magic_breakthrough"):
        events.append({
            "id": "magic_breakthrough",
            "title": "The Arcane Awakening",
            "framework": "world_event",
            "text": "A ritual you helped develop has succeeded beyond expectations. Magic is now accessible to everyone.",
            "choices": [
                {"id": "open", "label": "Open the gates", "effects": {"reputation": 5, "world_flags": {"magic_breakthrough": True}, "unlocks": ["public_magic"], "faction_changes": {"community": 10}}},
                {"id": "control", "label": "Keep it controlled", "effects": {"world_flags": {"magic_breakthrough": True}, "unlocks": ["controlled_magic"], "faction_changes": {"government": 10}}},
            ],
        })

    return events