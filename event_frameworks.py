"""Event Framework System for Riverton V1.

Reusable logic templates that events reference. New events can be added as
JSON data without changing Python code — the framework handler applies the
state changes deterministically.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from game_schema import normalize_era


class FrameworkError(ValueError):
    """Raised when an event framework cannot be resolved or applied."""


def handle_parent_decision(engine, event: dict[str, Any], choice_id: str) -> dict[str, Any]:
    """Handle parent-decision framework events.

    Applies parent strictness/support logic to school decisions.
    """
    parents = engine.state.get("parents", {"strictness": 0.5, "support": 0.5})
    strictness = float(parents.get("strictness", 0.5))
    choice = next((c for c in event.get("choices", []) if c.get("id") == choice_id), None)
    if not choice:
        raise FrameworkError(f"Choice '{choice_id}' not found in event '{event.get('id')}'")

    effects = deepcopy(choice.get("effects", {}))

    # Parent strictness can override a "refuse" choice
    if choice_id in ("no_school", "refuse", "push_back") and strictness >= 0.7:
        effects.setdefault("flags", {})["parent_forced"] = True
        effects.setdefault("flags", {})["school_forced"] = True
        effects.setdefault("education", {})["status"] = "forced"
        effects.setdefault("education", {})["school_unlocked"] = True

    # Parent support can boost positive choices
    support = float(parents.get("support", 0.5))
    if choice_id in ("yes_school", "go", "keep_school") and support >= 0.6:
        effects.setdefault("flags", {})["parent_supported"] = True
        effects.setdefault("reputation", 0)
        effects["reputation"] = effects.get("reputation", 0) + 1

    engine._apply_effects(effects)
    return effects


def handle_career_step(engine, event: dict[str, Any], choice_id: str) -> dict[str, Any]:
    """Handle career-step framework events.

    Applies career progression, skill gains, and unlocks next stages.
    """
    choice = next((c for c in event.get("choices", []) if c.get("id") == choice_id), None)
    if not choice:
        raise FrameworkError(f"Choice '{choice_id}' not found in event '{event.get('id')}'")

    effects = deepcopy(choice.get("effects", {}))
    engine._apply_effects(effects)

    # Career chain progression
    career_id = event.get("career_id")
    stage_id = event.get("stage_id")
    if career_id and stage_id:
        career_tracks = engine.state.setdefault("career_tracks", {})
        career = career_tracks.setdefault(career_id, {"stages_completed": [], "current_stage": None})
        if stage_id not in career["stages_completed"]:
            career["stages_completed"].append(stage_id)
        career["current_stage"] = stage_id
        engine._log("CAREER", f"Career '{career_id}' advanced to stage '{stage_id}'")

    return effects


def handle_relationship_test(engine, event: dict[str, Any], choice_id: str) -> dict[str, Any]:
    """Handle relationship-test framework events.

    Applies trust/affinity changes and records NPC memory.
    """
    choice = next((c for c in event.get("choices", []) if c.get("id") == choice_id), None)
    if not choice:
        raise FrameworkError(f"Choice '{choice_id}' not found in event '{event.get('id')}'")

    effects = deepcopy(choice.get("effects", {}))
    engine._apply_effects(effects)

    # Record NPC memory for involved NPCs
    npc_id = event.get("npc_id")
    if npc_id:
        npc = engine._npc(npc_id)
        engine._memory(
            f"{npc.get('name', npc_id)}: {choice.get('label', 'interaction')}",
            tags=[npc_id, "relationship"],
            linked_entities=[npc_id],
            importance=2,
        )

    return effects


def handle_world_event(engine, event: dict[str, Any], choice_id: str) -> dict[str, Any]:
    """Handle world-event framework events.

    Applies global state changes, faction shifts, and menu swaps.
    """
    choice = next((c for c in event.get("choices", []) if c.get("id") == choice_id), None)
    if not choice:
        raise FrameworkError(f"Choice '{choice_id}' not found in event '{event.get('id')}'")

    effects = deepcopy(choice.get("effects", {}))
    engine._apply_effects(effects)

    # Apply world-level effects
    world = engine.state.setdefault("world", {})
    world_flags = effects.get("world_flags", {})
    if world_flags:
        world.setdefault("global_flags", {}).update(world_flags)
        engine._log("WORLD", f"World flags updated: {world_flags}")

    # Faction changes
    faction_changes = effects.get("faction_changes", {})
    if faction_changes:
        factions = world.setdefault("factions", {})
        for faction_id, delta in faction_changes.items():
            faction = factions.setdefault(faction_id, {"power": 50, "trust": 0})
            faction["power"] = max(0, min(100, faction.get("power", 50) + delta))
        engine._log("WORLD", f"Faction changes: {faction_changes}")

    # Unlocks
    unlocks = effects.get("unlocks", [])
    if unlocks:
        world.setdefault("unlocks", {}).update({u: True for u in unlocks})
        engine._log("WORLD", f"Unlocked: {unlocks}")

    # Menu swaps
    menu_swaps = effects.get("menu_swap", {})
    if menu_swaps:
        world.setdefault("menu_swaps", {}).update(menu_swaps)
        engine._log("WORLD", f"Menu swaps: {menu_swaps}")

    return effects


def handle_life_milestone(engine, event: dict[str, Any], choice_id: str) -> dict[str, Any]:
    """Handle life-milestone framework events.

    Applies age/life-stage changes and major stat shifts.
    """
    choice = next((c for c in event.get("choices", []) if c.get("id") == choice_id), None)
    if not choice:
        raise FrameworkError(f"Choice '{choice_id}' not found in event '{event.get('id')}'")

    effects = deepcopy(choice.get("effects", {}))
    engine._apply_effects(effects)

    # Life milestone memory with high importance
    engine._memory(
        f"Life milestone: {event.get('title', 'Unknown')}",
        tags=["milestone", "life"],
        importance=5,
    )

    return effects


def handle_random_encounter(engine, event: dict[str, Any], choice_id: str) -> dict[str, Any]:
    """Handle random-encounter framework events.

    Standard stat/NPC/flags effects with memory recording.
    """
    choice = next((c for c in event.get("choices", []) if c.get("id") == choice_id), None)
    if not choice:
        raise FrameworkError(f"Choice '{choice_id}' not found in event '{event.get('id')}'")

    effects = deepcopy(choice.get("effects", {}))
    engine._apply_effects(effects)

    engine._memory(
        f"{event.get('title', 'Event')}: {choice.get('label', 'choice')}",
        tags=[event.get("id", "event")],
        importance=1,
    )

    return effects


# Framework registry
FRAMEWORKS: dict[str, dict[str, Any]] = {
    "parent_decision": {
        "handler": handle_parent_decision,
        "requires": ["parents"],
        "description": "Parent-driven decisions about school, discipline, and support.",
    },
    "career_step": {
        "handler": handle_career_step,
        "requires": ["career_tracks"],
        "description": "Career chain progression steps with skill and reputation gains.",
    },
    "relationship_test": {
        "handler": handle_relationship_test,
        "requires": ["npcs"],
        "description": "Relationship-building or testing events with NPC memory recording.",
    },
    "world_event": {
        "handler": handle_world_event,
        "requires": ["world"],
        "description": "World-changing events that alter global state, factions, and unlocks.",
    },
    "life_milestone": {
        "handler": handle_life_milestone,
        "requires": ["player"],
        "description": "Major life milestones like graduation, marriage, birth, or death.",
    },
    "random_encounter": {
        "handler": handle_random_encounter,
        "requires": [],
        "description": "Generic random encounters with standard stat effects.",
    },
}


def get_framework(framework_id: str) -> dict[str, Any] | None:
    """Get a framework definition by ID."""
    return FRAMEWORKS.get(framework_id)


def resolve_framework(engine, event: dict[str, Any], choice_id: str) -> dict[str, Any]:
    """Resolve an event using its framework handler.

    Args:
        engine: The GameEngine instance.
        event: The event definition with a 'framework' key.
        choice_id: The chosen choice ID.

    Returns:
        The effects that were applied.

    Raises:
        FrameworkError: If the framework is unknown or the choice is invalid.
    """
    framework_id = event.get("framework", "random_encounter")
    framework = FRAMEWORKS.get(framework_id)
    if not framework:
        raise FrameworkError(f"Unknown framework: '{framework_id}'")

    handler: Callable = framework["handler"]
    return handler(engine, event, choice_id)