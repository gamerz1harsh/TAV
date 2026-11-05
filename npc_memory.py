"""Per-NPC Memory System for Riverton V1.

Each NPC has its own memory file storing interactions, attitudes, grudges,
favors owed, and promises. NPC reactions depend on what they remember.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
GAMES_DIR = DATA_DIR / "games"


def _default_npc_memory(npc_id: str) -> dict[str, Any]:
    """Create a default memory structure for an NPC."""
    return {
        "npc_id": npc_id,
        "memories": [],
        "attitude": {
            "overall": "neutral",
            "trust_level": 0,
            "affinity_level": 0,
            "grudges": [],
            "favors_owed": 0,
            "favors_given": 0,
            "promises_made": [],
            "promises_kept": 0,
            "promises_broken": 0,
        },
    }


def _get_npc_memory_path(game_folder: Path, npc_id: str) -> Path:
    """Get the memory file path for an NPC in a game folder."""
    return game_folder / f"npc_memory_{npc_id}.json"


def load_npc_memory(game_folder: Path, npc_id: str) -> dict[str, Any]:
    """Load an NPC's memory file, or create a default if missing."""
    path = _get_npc_memory_path(game_folder, npc_id)
    if not path.exists():
        return _default_npc_memory(npc_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("npc_id") == npc_id:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return _default_npc_memory(npc_id)


def save_npc_memory(game_folder: Path, memory: dict[str, Any]) -> bool:
    """Save an NPC's memory file."""
    try:
        game_folder.mkdir(exist_ok=True)
        path = _get_npc_memory_path(game_folder, memory.get("npc_id", "unknown"))
        path.write_text(json.dumps(memory, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def add_npc_memory(
    game_folder: Path,
    npc_id: str,
    text: str,
    *,
    memory_type: str = "interaction",
    importance: int = 1,
    player_action: str | None = None,
    player_attitude: str | None = None,
    npc_reaction: str | None = None,
    relationship_delta: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Add a memory record to an NPC's memory file.

    Args:
        game_folder: The game folder path.
        npc_id: The NPC's ID.
        text: The memory text.
        memory_type: Type of memory (interaction, conversation, gift, etc.).
        importance: 1 (ordinary) to 5 (critical).
        player_action: What the player did.
        player_attitude: How the player behaved.
        npc_reaction: How the NPC reacted.
        relationship_delta: Changes to trust/affinity.

    Returns:
        The updated NPC memory structure.
    """
    memory = load_npc_memory(game_folder, npc_id)

    record = {
        "id": f"mem_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": datetime.now().isoformat(),
        "type": memory_type,
        "text": text,
        "importance": max(1, min(5, importance)),
        "player_action": player_action,
        "player_attitude": player_attitude,
        "npc_reaction": npc_reaction,
        "relationship_delta": relationship_delta or {},
    }

    memory["memories"].append(record)
    # Keep only the last 50 memories per NPC
    memory["memories"] = memory["memories"][-50:]

    # Update attitude based on relationship delta
    attitude = memory["attitude"]
    delta = relationship_delta or {}
    attitude["trust_level"] = max(-5, min(5, attitude.get("trust_level", 0) + delta.get("trust", 0)))
    attitude["affinity_level"] = max(-5, min(5, attitude.get("affinity_level", 0) + delta.get("affinity", 0)))

    # Update overall attitude
    combined = attitude["trust_level"] + attitude["affinity_level"]
    if combined >= 4:
        attitude["overall"] = "trusting"
    elif combined >= 2:
        attitude["overall"] = "friendly"
    elif combined <= -4:
        attitude["overall"] = "hostile"
    elif combined <= -2:
        attitude["overall"] = "cold"
    else:
        attitude["overall"] = "neutral"

    # Track favors
    if player_action == "help":
        attitude["favors_owed"] = attitude.get("favors_owed", 0) + 1
    if player_action == "ask_favor":
        attitude["favors_given"] = attitude.get("favors_given", 0) + 1

    # Track grudges
    if player_attitude in ("betray", "threaten", "lie", "steal"):
        attitude["grudges"].append({
            "text": text,
            "timestamp": record["timestamp"],
            "severity": importance,
        })

    save_npc_memory(game_folder, memory)
    return memory


def get_npc_reaction(
    game_folder: Path,
    npc_id: str,
    npc: dict[str, Any],
    action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get an NPC's reaction to a player action based on memory.

    Args:
        game_folder: The game folder path.
        npc_id: The NPC's ID.
        npc: The NPC's current state.
        action: The action the player is attempting.
        context: Additional context.

    Returns:
        A dict with 'text', 'bonus', 'penalty', and 'attitude'.
    """
    memory = load_npc_memory(game_folder, npc_id)
    attitude = memory["attitude"]
    overall = attitude.get("overall", "neutral")

    # Base reaction from relationship values
    trust = npc.get("trust", 0)
    affinity = npc.get("affinity", 0)

    reaction = {
        "text": "",
        "bonus": 0,
        "penalty": 0,
        "attitude": overall,
    }

    # Action-specific reactions based on memory
    if action == "help":
        if attitude.get("favors_owed", 0) > 0:
            reaction["text"] = "You've helped me before. I trust you."
            reaction["bonus"] = 1
        elif attitude.get("grudges"):
            reaction["text"] = "You didn't help me last time."
            reaction["penalty"] = -1
        else:
            reaction["text"] = "Thanks for offering to help."
            reaction["bonus"] = 0

    elif action == "talk":
        if overall == "trusting":
            reaction["text"] = "Good to see you. I've been thinking about what you said."
            reaction["bonus"] = 1
        elif overall == "hostile":
            reaction["text"] = "What do you want?"
            reaction["penalty"] = -1
        else:
            reaction["text"] = "How's your day going?"
            reaction["bonus"] = 0

    elif action == "work":
        if attitude.get("favors_owed", 0) > 0:
            reaction["text"] = "We make a good team."
            reaction["bonus"] = 1
        else:
            reaction["text"] = "Let's get to it."
            reaction["bonus"] = 0

    elif action == "ask_favor":
        if attitude.get("favors_owed", 0) > 0:
            reaction["text"] = "You've done a lot for me. Of course."
            reaction["bonus"] = 2
        elif attitude.get("grudges"):
            reaction["text"] = "I remember what happened before."
            reaction["penalty"] = -2
        else:
            reaction["text"] = "I'll see what I can do."
            reaction["bonus"] = 0

    elif action == "gift":
        if attitude.get("grudges"):
            reaction["text"] = "A gift won't fix everything."
            reaction["penalty"] = -1
        else:
            reaction["text"] = "You didn't have to. Thank you."
            reaction["bonus"] = 1

    elif action == "betray":
        reaction["text"] = "I trusted you."
        reaction["penalty"] = -3

    # Default fallback
    if not reaction["text"]:
        reaction["text"] = f"{npc.get('name', npc_id)} acknowledges you."

    return reaction


def get_npc_memory_summary(game_folder: Path, npc_id: str) -> dict[str, Any]:
    """Get a summary of an NPC's memory for UI display."""
    memory = load_npc_memory(game_folder, npc_id)
    attitude = memory["attitude"]
    recent = memory["memories"][-5:]

    return {
        "npc_id": npc_id,
        "overall": attitude.get("overall", "neutral"),
        "trust_level": attitude.get("trust_level", 0),
        "affinity_level": attitude.get("affinity_level", 0),
        "grudges": len(attitude.get("grudges", [])),
        "favors_owed": attitude.get("favors_owed", 0),
        "favors_given": attitude.get("favors_given", 0),
        "recent_memories": [
            {"text": m.get("text", ""), "importance": m.get("importance", 1), "timestamp": m.get("timestamp", "")}
            for m in recent
        ],
    }