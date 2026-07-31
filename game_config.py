"""Global game configuration loading and per-game folder management for Riverton.

This module reads the central `data/game_config.json` file which contains ALL
game data (NPC templates, origins, locations, seasons, main events, random
events, and NPC arcs). It also manages per-game folders where each game's
generated data (map, NPCs, scenario, save state, memories) is stored.

Per-game folder structure:
    data/games/{player_name}_{YYYYMMDD_HHMMSS}/
        map.json          - The generated map locations
        npcs.json         - The generated NPC list
        scenario.json     - The starting scenario description
        events.json       - Game events data
        save_state.json   - The game save state
        memories.jsonl    - Structured memories for this game
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = DATA_DIR / "game_config.json"
GAMES_DIR = DATA_DIR / "games"
SAVE_FILE = DATA_DIR / "save_state.json"  # Backward-compatible default save location

# ---------------------------------------------------------------------------
# Hardcoded fallback defaults (used only when game_config.json is missing)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    "seasons": ["Spring", "Summer", "Autumn", "Winter"],
    "base_locations": {
        "apartment": "Apartment",
        "cafe": "Juniper Cafe",
        "college": "Community College",
    },
    "npc_templates": [
        {"id": "maya", "name": "Maya Ortiz", "role": "Your roommate", "location": "apartment", "affinity": 2, "trust": 1, "description": "A practical designer who values people showing up."},
        {"id": "leo", "name": "Leo Chen", "role": "Classmate", "location": "college", "affinity": 1, "trust": 0, "description": "An ambitious student who knows every deadline."},
        {"id": "priya", "name": "Priya Shah", "role": "Cafe manager", "location": "cafe", "affinity": 0, "trust": 0, "description": "A sharp observer who notices consistent work."},
        {"id": "dr_ellis", "name": "Dr. Ellis Reed", "role": "Career mentor", "location": "college", "affinity": 0, "trust": 0, "description": "A patient lecturer with local connections."},
        {"id": "sam", "name": "Sam Walker", "role": "Community organizer", "location": "cafe", "affinity": 0, "trust": 0, "description": "A determined organizer working on housing."},
        {"id": "nora", "name": "Nora Blake", "role": "Local rival", "location": "cafe", "affinity": -1, "trust": 0, "description": "A competitive regular with a sharp opinion."},
    ],
    "origins": [
        {"id": "scholarship_student", "name": "Scholarship Student", "tag": "Academic head start", "description": "You arrived with academic momentum, but very little financial room.", "effects": {"skill": 2, "money": -2}, "known_npc": "leo"},
        {"id": "cafe_worker", "name": "Cafe Worker", "tag": "Earned connections", "description": "You know how to earn a shift and read a room.", "effects": {"money": 2, "energy": -1}, "known_npc": "priya"},
        {"id": "local_resident", "name": "Local Resident", "tag": "A familiar face", "description": "Your history in Riverton gives you a voice from day one.", "effects": {"reputation": 2}, "known_npc": "sam"},
        {"id": "new_arrival", "name": "New Arrival", "tag": "A clean slate", "description": "You are free to reinvent yourself without old expectations.", "effects": {"energy": 1}, "known_npc": None},
    ],
    "main_events": [],
    "random_events": [],
    "npc_arcs": {},
}

# Cache for the loaded config
_config_cache: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Global config loading
# ---------------------------------------------------------------------------

def load_game_config(force_reload: bool = False) -> dict[str, Any]:
    """Load the global game configuration from data/game_config.json.

    Falls back to built-in defaults if the file is missing or invalid.

    Args:
        force_reload: If True, ignore the cached config and reload from disk.

    Returns:
        The configuration dictionary.
    """
    global _config_cache
    if _config_cache is not None and not force_reload:
        return _config_cache

    if not CONFIG_FILE.exists():
        _config_cache = _DEFAULT_CONFIG
        return _config_cache

    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            _config_cache = _DEFAULT_CONFIG
            return _config_cache

        # Merge with defaults to ensure all keys exist
        merged = {**_DEFAULT_CONFIG, **data}
        for key in ("seasons", "base_locations", "npc_templates", "origins", "main_events", "random_events", "npc_arcs"):
            if not isinstance(merged.get(key), (list, dict)):
                merged[key] = _DEFAULT_CONFIG.get(key, [] if key not in ("base_locations", "npc_arcs") else {})
        _config_cache = merged
        return merged
    except (json.JSONDecodeError, OSError):
        _config_cache = _DEFAULT_CONFIG
        return _config_cache


def reload_game_config() -> dict[str, Any]:
    """Force-reload the game configuration from disk."""
    return load_game_config(force_reload=True)


# ---------------------------------------------------------------------------
# Accessors for game data
# ---------------------------------------------------------------------------

def get_seasons() -> list[str]:
    """Return the list of season names."""
    return list(load_game_config().get("seasons", ["Spring", "Summer", "Autumn", "Winter"]))


def get_base_locations() -> dict[str, str]:
    """Return the base location dictionary (id -> display name)."""
    data = load_game_config().get("base_locations", {})
    if not isinstance(data, dict):
        return {"apartment": "Apartment", "cafe": "Juniper Cafe", "college": "Community College"}
    return dict(data)


def get_npc_templates() -> list[dict[str, Any]]:
    """Return the default NPC templates."""
    return list(load_game_config().get("npc_templates", []))


def get_origins() -> list[dict[str, Any]]:
    """Return the origin definitions."""
    return list(load_game_config().get("origins", []))


def get_main_events() -> list[dict[str, Any]]:
    """Return the main seasonal events."""
    return list(load_game_config().get("main_events", []))


def get_random_events() -> list[dict[str, Any]]:
    """Return the random events list."""
    return list(load_game_config().get("random_events", []))


def get_npc_arcs() -> dict[str, Any]:
    """Return the NPC arc definitions."""
    data = load_game_config().get("npc_arcs", {})
    if not isinstance(data, dict):
        return {}
    return dict(data)


def save_game_config(config: dict[str, Any]) -> bool:
    """Write the configuration back to data/game_config.json.

    Returns:
        True on success, False on failure.
    """
    global _config_cache
    try:
        DATA_DIR.mkdir(exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        _config_cache = config
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Per-game folder management
# ---------------------------------------------------------------------------

def _sanitize_name(name: str) -> str:
    """Sanitize a player name for use in a folder name."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:40] or "Player"


def create_game_folder(player_name: str) -> Path:
    """Create a per-game folder named '{player_name}_{timestamp}'.

    Args:
        player_name: The player's name.

    Returns:
        The path to the created game folder.
    """
    GAMES_DIR.mkdir(exist_ok=True)
    safe_name = _sanitize_name(player_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{safe_name}_{timestamp}"
    game_folder = GAMES_DIR / folder_name
    game_folder.mkdir(exist_ok=False)
    return game_folder


def get_game_folder(player_name: str, folder_name: str | None = None) -> Path | None:
    """Find a game folder by player name (latest match) or exact folder name.

    Args:
        player_name: The player's name to search for (fuzzy match on prefix).
        folder_name: An exact folder name to look for.

    Returns:
        Path to the game folder, or None if not found.
    """
    if not GAMES_DIR.exists():
        return None

    if folder_name:
        candidate = GAMES_DIR / folder_name
        if candidate.is_dir():
            return candidate
        return None

    if not player_name:
        return None

    safe_name = _sanitize_name(player_name)
    # Try prefix match first
    matches = sorted(
        [p for p in GAMES_DIR.iterdir() if p.is_dir() and p.name.startswith(safe_name)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if matches:
        return matches[0]

    # Fallback: fuzzy match (case-insensitive contains)
    lower = player_name.lower()
    matches = sorted(
        [p for p in GAMES_DIR.iterdir() if p.is_dir() and lower in p.name.lower()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def list_games() -> list[dict[str, Any]]:
    """List all saved game folders with metadata.

    Returns:
        A list of dicts with keys: folder, player_name, created, has_save.
    """
    if not GAMES_DIR.exists():
        return []

    games = []
    for folder in sorted(GAMES_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        # Extract player name from folder name: {PlayerName}_{timestamp}
        parts = folder.name.rsplit("_", 2)
        player_name = parts[0] if parts else folder.name
        created = folder.stat().st_mtime
        has_save = (folder / "save_state.json").exists()
        games.append({
            "folder": folder.name,
            "player_name": player_name,
            "created": datetime.fromtimestamp(created).isoformat(),
            "has_save": has_save,
        })
    return games


def delete_game_folder(folder_name: str) -> bool:
    """Delete a game folder and its contents.

    Args:
        folder_name: The exact folder name to delete.

    Returns:
        True on success, False on failure.
    """
    game_folder = GAMES_DIR / folder_name
    if not game_folder.is_dir():
        return False
    try:
        import shutil
        shutil.rmtree(game_folder)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Per-game JSON file I/O
# ---------------------------------------------------------------------------

def write_game_json(folder: Path, filename: str, data: Any) -> bool:
    """Write data to a JSON file inside a game folder.

    Args:
        folder: The game folder path.
        filename: The file name (e.g., 'map.json').
        data: The data to write.

    Returns:
        True on success, False on failure.
    """
    try:
        folder.mkdir(exist_ok=True)
        file_path = folder / filename
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except (OSError, TypeError):
        return False


def read_game_json(folder: Path, filename: str, default: Any = None) -> Any:
    """Read data from a JSON file inside a game folder.

    Args:
        folder: The game folder path.
        filename: The file name (e.g., 'map.json').
        default: Value to return if the file doesn't exist or is invalid.

    Returns:
        The parsed data, or the default value.
    """
    file_path = folder / filename
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def get_save_file_for_game(folder: Path) -> Path:
    """Return the save file path for a game folder."""
    return folder / "save_state.json"


def get_memories_file_for_game(folder: Path) -> Path:
    """Return the memories file path for a game folder."""
    return folder / "memories.jsonl"


# ---------------------------------------------------------------------------
# Per-game data file names (constants)
# ---------------------------------------------------------------------------

MAP_FILE = "map.json"
NPCS_FILE = "npcs.json"
SCENARIO_FILE = "scenario.json"
EVENTS_FILE = "events.json"
CHARACTER_FILE = "character.json"


def save_game_data(folder: Path, **data: Any) -> None:
    """Convenience method to save multiple game data files at once.

    Usage:
        save_game_data(folder, map=map_data, npcs=npcs_list, scenario=scenario_text)
    """
    for filename, content in data.items():
        full_name = f"{filename}.json"
        write_game_json(folder, full_name, content)
