"""Era Data Loader for Riverton V1.

Lazy-loads era-specific data files (events, jobs, NPCs, themes) on demand.
This prevents loading all content at startup and keeps memory usage low
as the game grows with more eras and events.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from game_schema import normalize_era

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"


class EraDataLoader:
    """Lazy-loads era-specific data files with caching."""

    def __init__(self, era: str = "modern") -> None:
        self.era = normalize_era(era)
        self._cache: dict[str, Any] = {}

    def set_era(self, era: str) -> None:
        """Switch the active era and clear the cache."""
        new_era = normalize_era(era)
        if new_era != self.era:
            self.era = new_era
            self._cache.clear()

    def _load_json(self, category: str, filename: str, default: Any = None) -> Any:
        """Load a JSON file from the data directory with caching."""
        cache_key = f"{category}/{filename}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = DATA_DIR / category / filename
        if not file_path.exists():
            self._cache[cache_key] = default
            return default

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            self._cache[cache_key] = data
            return data
        except (json.JSONDecodeError, OSError):
            self._cache[cache_key] = default
            return default

    # ------------------------------------------------------------------
    # Era profiles
    # ------------------------------------------------------------------

    def get_era_profile(self) -> dict[str, Any]:
        """Get the era profile (menu slots, labels, etc.)."""
        return self._load_json("eras", f"{self.era}.json", {})

    def get_era_theme(self) -> dict[str, Any]:
        """Get the era theme (colors, fonts, UI labels)."""
        return self._load_json("themes", f"{self.era}_theme.json", {})

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def get_age_events(self, min_age: int | None = None, max_age: int | None = None) -> list[dict[str, Any]]:
        """Get age-triggered events, optionally filtered by age range."""
        data = self._load_json("events", "age_events.json", {})
        events = data.get("age_events", []) if isinstance(data, dict) else []
        if min_age is not None or max_age is not None:
            events = [
                e for e in events
                if (min_age is None or e.get("min_age", 0) >= min_age)
                and (max_age is None or e.get("max_age", 999) <= max_age)
            ]
        return events

    def get_life_events(self) -> list[dict[str, Any]]:
        """Get major life events (marriage, birth, death, etc.)."""
        data = self._load_json("events", "life_events.json", {})
        return data.get("life_events", []) if isinstance(data, dict) else []

    def get_world_events(self) -> list[dict[str, Any]]:
        """Get world-changing events."""
        data = self._load_json("events", "world_events.json", {})
        return data.get("world_events", []) if isinstance(data, dict) else []

    def get_random_events(self) -> list[dict[str, Any]]:
        """Get generic random events for this era."""
        data = self._load_json("events", "random_events.json", {})
        return data.get("random_events", []) if isinstance(data, dict) else []

    def get_all_events(self) -> list[dict[str, Any]]:
        """Get all events for this era (age + life + world + random)."""
        return (
            self.get_age_events()
            + self.get_life_events()
            + self.get_world_events()
            + self.get_random_events()
        )

    # ------------------------------------------------------------------
    # Careers & Jobs
    # ------------------------------------------------------------------

    def get_careers(self) -> list[dict[str, Any]]:
        """Get all career chain definitions for this era."""
        data = self._load_json("careers", f"{self.era}_careers.json", {})
        return data.get("careers", []) if isinstance(data, dict) else []

    def get_career(self, career_id: str) -> dict[str, Any] | None:
        """Get a specific career chain definition."""
        for career in self.get_careers():
            if career.get("id") == career_id:
                return career
        return None

    def get_jobs(self) -> list[dict[str, Any]]:
        """Get job listings for this era."""
        data = self._load_json("jobs", f"{self.era}_jobs.json", {})
        return data.get("jobs", []) if isinstance(data, dict) else []

    # ------------------------------------------------------------------
    # NPCs
    # ------------------------------------------------------------------

    def get_npc_templates(self) -> list[dict[str, Any]]:
        """Get NPC templates for this era."""
        data = self._load_json("npcs", f"{self.era}_npcs.json", {})
        return data.get("npcs", []) if isinstance(data, dict) else []

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()


# Global singleton for convenience
_loader: EraDataLoader | None = None


def get_era_loader(era: str | None = None) -> EraDataLoader:
    """Get the global era data loader instance."""
    global _loader
    if _loader is None:
        _loader = EraDataLoader(era or "modern")
    elif era is not None:
        _loader.set_era(era)
    return _loader