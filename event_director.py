"""Event Director V1 — deterministic scoring for Riverton.

The Event Director selects the most interesting eligible event based on
transparent scoring rather than random weighted selection. It logs all
candidates, scores, and selections to data/director_log.jsonl for debugging
and future balance tuning.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DIRECTOR_LOG = ROOT / "data" / "director_log.jsonl"


def _ensure_log_dir() -> None:
    DIRECTOR_LOG.parent.mkdir(exist_ok=True)


def _log_candidates(
    candidates: list[dict[str, Any]],
    scores: list[float],
    selected: dict[str, Any] | None,
    context: dict[str, Any],
) -> None:
    """Append a director decision record to the log file."""
    _ensure_log_dir()
    record = {
        "timestamp": datetime.now().isoformat(),
        "context_summary": {
            "location": context.get("player", {}).get("location"),
            "stats": context.get("player", {}).get("stats"),
            "season_index": context.get("season_index", -1),
            "flags": context.get("flags", {}),
        },
        "candidates": [
            {
                "id": c["id"],
                "title": c.get("title", ""),
                "score": round(s, 2),
                "requires": c.get("requires", {}),
                "weight": c.get("weight", 1),
            }
            for c, s in zip(candidates, scores)
        ],
        "selected_id": selected["id"] if selected else None,
    }
    with open(DIRECTOR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def score_event(
    event: dict[str, Any],
    context: dict[str, Any],
    recent_ids: set[str],
) -> float:
    """Compute a deterministic score for a single event candidate.

    Scoring formula:
        score = relevance_to_player * 3
              + relationship_tension * 2
              + path_progress * 2
              + novelty * 2
              - recently_seen_penalty * 4
    """
    player = context.get("player", {})
    stats = player.get("stats", {})
    flags = context.get("flags", {})
    npcs = {npc["id"]: npc for npc in context.get("npcs", [])}
    requires = event.get("requires", {})

    # --- relevance_to_player (0-3) ---
    relevance = 0.0
    # Matches current location
    if requires.get("location") and requires["location"] == player.get("location"):
        relevance += 1.0
    # Matches active flags
    required_flags = requires.get("flags", {})
    if required_flags:
        matching = sum(1 for f in required_flags if flags.get(f))
        if matching > 0:
            relevance += 1.0
    # Matches stat thresholds
    required_stats = requires.get("stat", {})
    if required_stats:
        meeting = sum(1 for s, v in required_stats.items() if stats.get(s, 0) >= v)
        if meeting > 0:
            relevance += 1.0

    # --- relationship_tension (0-2) ---
    tension = 0.0
    required_npcs = requires.get("npc", {})
    for npc_id, thresholds in required_npcs.items():
        npc = npcs.get(npc_id)
        if npc:
            # High trust or low affinity creates interesting tension
            if npc.get("trust", 0) >= 2:
                tension += 0.5
            if npc.get("affinity", 0) <= -1:
                tension += 0.5
            # Check if thresholds are met
            for field, minimum in thresholds.items():
                if npc.get(field, 0) >= minimum:
                    tension += 0.5
    tension = min(tension, 2.0)

    # --- path_progress (0-2) ---
    path_progress = 0.0
    # Events that advance known paths
    if event.get("tags"):
        path_tags = {"study", "portfolio", "campaign", "cafe", "community", "mentor"}
        if path_tags & set(event.get("tags", [])):
            path_progress += 1.0
    # Events that match origin
    origin_id = context.get("origin", {}).get("id", "")
    if origin_id and event.get("tags"):
        origin_tags = {
            "scholarship_student": {"study", "academic", "mentor"},
            "cafe_worker": {"cafe", "work", "money"},
            "local_resident": {"community", "campaign", "reputation"},
            "new_arrival": {"explore", "meet", "discover"},
        }
        matching_origin = origin_tags.get(origin_id, set()) & set(event.get("tags", []))
        if matching_origin:
            path_progress += 1.0

    # --- novelty (0-2) ---
    novelty = 0.0
    if event["id"] not in recent_ids:
        novelty += 1.0
    # Prefer events not seen this game
    seen = context.get("seen_random_events", [])
    if event["id"] not in seen:
        novelty += 1.0

    # --- recently_seen_penalty (0-1) ---
    penalty = 1.0 if event["id"] in recent_ids else 0.0

    score = relevance * 3 + tension * 2 + path_progress * 2 + novelty * 2 - penalty * 4
    return max(0.0, score)


def select_event(
    candidates: list[dict[str, Any]],
    context: dict[str, Any],
    recent_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    """Score all candidates and return the highest-scoring event.

    If no candidates are provided, returns None.
    Logs all candidates, scores, and the selection to director_log.jsonl.
    """
    if not candidates:
        return None

    if recent_ids is None:
        recent_ids = set()

    scored = [(event, score_event(event, context, recent_ids)) for event in candidates]
    scored.sort(key=lambda item: item[1], reverse=True)

    selected = scored[0][0] if scored else None

    _log_candidates(candidates, [s for _, s in scored], selected, context)

    return selected
