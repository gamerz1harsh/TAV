"""Career Chain System for Riverton V1.

Careers are hidden progression chains discovered through play. Each career
has stages with requirements, unlocks, effects, and events. Job listings
appear only when the player has unlocked the relevant stage.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from era_data_loader import get_era_loader


class CareerError(ValueError):
    """Raised when a career action is invalid."""


def get_available_careers(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all career definitions available for the current era."""
    era = state.get("player", {}).get("era", "modern")
    loader = get_era_loader(era)
    return loader.get_careers()


def get_career_progress(state: dict[str, Any], career_id: str) -> dict[str, Any]:
    """Get the player's progress in a specific career chain."""
    career_tracks = state.get("career_tracks", {})
    return career_tracks.get(career_id, {"stages_completed": [], "current_stage": None})


def get_eligible_career_stages(state: dict[str, Any], career: dict[str, Any]) -> list[dict[str, Any]]:
    """Get career stages that are eligible to trigger based on requirements.

    A stage is eligible if:
    - It hasn't been completed yet
    - Its requirements are met
    - Its prerequisites (unlocks) are satisfied
    """
    progress = get_career_progress(state, career.get("id", ""))
    completed = set(progress.get("stages_completed", []))
    flags = state.get("flags", {})
    stats = state.get("player", {}).get("stats", {})
    age = int(state.get("player", {}).get("age", 18))

    eligible = []
    for stage in career.get("stages", []):
        stage_id = stage.get("id", "")
        if stage_id in completed:
            continue

        # Check prerequisites (unlocks)
        unlocks = stage.get("unlocks", [])
        if unlocks and not all(u in completed for u in unlocks):
            continue

        # Check requirements
        reqs = stage.get("requirements", {})
        if not _meets_requirements(reqs, age, stats, flags, state):
            continue

        eligible.append(stage)

    return eligible


def _meets_requirements(
    reqs: dict[str, Any],
    age: int,
    stats: dict[str, Any],
    flags: dict[str, Any],
    state: dict[str, Any],
) -> bool:
    """Check if the player meets a stage's requirements."""
    # Age requirement
    if "age" in reqs and age < reqs["age"]:
        return False

    # Stat requirements
    for stat, minimum in reqs.get("stat", {}).items():
        if stats.get(stat, 0) < minimum:
            return False

    # Flag requirements
    for flag in reqs.get("flags", []):
        if not flags.get(flag):
            return False

    # Money requirement
    if "money" in reqs and stats.get("money", 0) < reqs["money"]:
        return False

    # NPC relationship requirements
    for npc_id, thresholds in reqs.get("npc", {}).items():
        npc = next((n for n in state.get("npcs", []) if n.get("id") == npc_id), None)
        if not npc:
            return False
        for field, minimum in thresholds.items():
            if npc.get(field, 0) < minimum:
                return False

    return True


def get_available_jobs(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Get job listings that the player is currently eligible for."""
    era = state.get("player", {}).get("era", "modern")
    loader = get_era_loader(era)
    all_jobs = loader.get_jobs()

    flags = state.get("flags", {})
    stats = state.get("player", {}).get("stats", {})
    age = int(state.get("player", {}).get("age", 18))
    career_tracks = state.get("career_tracks", {})

    available = []
    for job in all_jobs:
        reqs = job.get("requirements", {})
        if not _meets_requirements(reqs, age, stats, flags, state):
            continue
        # Check career track requirements
        career_req = job.get("career")
        if career_req:
            progress = career_tracks.get(career_req, {})
            required_stage = job.get("career_stage")
            if required_stage and required_stage not in progress.get("stages_completed", []):
                continue
        available.append(job)

    return available


def get_locked_jobs(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Get job listings that are locked but show hints."""
    era = state.get("player", {}).get("era", "modern")
    loader = get_era_loader(era)
    all_jobs = loader.get_jobs()

    flags = state.get("flags", {})
    stats = state.get("player", {}).get("stats", {})
    age = int(state.get("player", {}).get("age", 18))
    career_tracks = state.get("career_tracks", {})

    locked = []
    for job in all_jobs:
        reqs = job.get("requirements", {})
        if _meets_requirements(reqs, age, stats, flags, state):
            continue
        # Check career track requirements
        career_req = job.get("career")
        if career_req:
            progress = career_tracks.get(career_req, {})
            required_stage = job.get("career_stage")
            if required_stage and required_stage not in progress.get("stages_completed", []):
                locked.append({
                    "id": job.get("id"),
                    "name": job.get("name", "???"),
                    "hint": job.get("hint", "Keep building your path."),
                    "locked": True,
                })
                continue
        locked.append({
            "id": job.get("id"),
            "name": job.get("name", "???"),
            "hint": job.get("hint", "Requirements not met yet."),
            "locked": True,
        })

    return locked


def check_career_triggers(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Check all careers for eligible stages and return their events.

    Returns a list of event definitions that can be fed to the Event Director.
    """
    careers = get_available_careers(state)
    triggered_events = []

    for career in careers:
        career_id = career.get("id", "")
        eligible_stages = get_eligible_career_stages(state, career)
        for stage in eligible_stages:
            event = stage.get("event", {})
            if event:
                # Tag the event with career and stage info
                event["career_id"] = career_id
                event["stage_id"] = stage.get("id")
                event["framework"] = stage.get("event_framework", "career_step")
                event["_is_career_event"] = True
                triggered_events.append(event)

    return triggered_events


def apply_job_work(state: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Apply the effects of working a job.

    Returns the effects applied.
    """
    effects = {
        "money": job.get("pay", 1),
        "energy": -job.get("energy_cost", 1),
        "skill": job.get("skill_gain", 0),
        "reputation": job.get("reputation_gain", 0),
    }
    return effects


def get_career_summary(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Get a summary of all career progress for UI display."""
    careers = get_available_careers(state)
    career_tracks = state.get("career_tracks", {})
    summary = []

    for career in careers:
        career_id = career.get("id", "")
        progress = career_tracks.get(career_id, {"stages_completed": [], "current_stage": None})
        stages = career.get("stages", [])
        total_stages = len(stages)
        completed_count = len(progress.get("stages_completed", []))

        # Find current stage name
        current_stage_name = None
        current_stage_id = progress.get("current_stage")
        if current_stage_id:
            for stage in stages:
                if stage.get("id") == current_stage_id:
                    current_stage_name = stage.get("name")
                    break

        summary.append({
            "id": career_id,
            "name": career.get("name", career_id),
            "description": career.get("description", ""),
            "progress": completed_count,
            "total_stages": total_stages,
            "percentage": (completed_count / total_stages * 100) if total_stages > 0 else 0,
            "current_stage": current_stage_name,
            "unlocked": completed_count > 0,
            "completed": completed_count >= total_stages,
        })

    return summary