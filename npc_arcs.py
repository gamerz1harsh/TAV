"""NPC story arcs and milestone progression for Riverton.

Each NPC has a story arc with milestones that trigger based on relationship
thresholds, flags, and seasonal progression. Arc events integrate with the
Event Director for selection and the memory system for continuity.
"""
from __future__ import annotations

from typing import Any

# Load NPC arcs from the central game configuration (data/game_config.json)
import game_config

NPC_ARCS: dict[str, dict[str, Any]] = game_config.get_npc_arcs()


def get_npc_arc(npc_id: str) -> dict[str, Any] | None:
    """Get the full arc definition for an NPC."""
    return NPC_ARCS.get(npc_id)


def get_available_milestones(
    npc_id: str,
    npc_state: dict[str, Any],
    flags: dict[str, Any],
    completed_milestones: set[str],
) -> list[dict[str, Any]]:
    """Get milestones that are eligible to trigger for an NPC.

    Args:
        npc_id: The NPC's ID.
        npc_state: The NPC's current state (trust, affinity, etc.).
        flags: Current game flags.
        completed_milestones: Set of milestone IDs already completed.

    Returns:
        List of milestone definitions that meet their trigger conditions.
    """
    arc = NPC_ARCS.get(npc_id)
    if not arc:
        return []

    available = []
    for milestone in arc.get("milestones", []):
        if milestone["id"] in completed_milestones:
            continue

        trigger = milestone.get("trigger", {})
        # Check trust threshold
        if "trust" in trigger and npc_state.get("trust", 0) < trigger["trust"]:
            continue
        # Check affinity threshold
        if "affinity" in trigger and npc_state.get("affinity", 0) < trigger["affinity"]:
            continue
        # Check required flags
        required_flags = trigger.get("flags", [])
        if required_flags and not all(flags.get(f) for f in required_flags):
            continue

        available.append(milestone)

    return available


def get_npc_arc_events(
    npcs: list[dict[str, Any]],
    flags: dict[str, Any],
    completed_milestones: set[str],
) -> list[dict[str, Any]]:
    """Collect all eligible arc events across all NPCs.

    Returns a list of event definitions that can be fed to the Event Director.
    """
    events = []
    for npc in npcs:
        npc_id = npc.get("id", "")
        milestones = get_available_milestones(npc_id, npc, flags, completed_milestones)
        for milestone in milestones:
            event = milestone.get("event", {})
            if event:
                # Tag the event with the NPC id for tracking
                event["npc_id"] = npc_id
                event["milestone_id"] = milestone["id"]
                events.append(event)
    return events
