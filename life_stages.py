"""Life Stage System for Riverton V1.

Each life stage (infant, toddler, child, teen, young adult, adult, senior)
has its own set of available actions, event pools, and progression rules.
"""
from __future__ import annotations

from typing import Any

LIFE_STAGES: dict[str, dict[str, Any]] = {
    "infant": {
        "min_age": 0,
        "max_age": 2,
        "label": "Infant",
        "actions": [
            {"id": "sleep", "label": "Sleep", "category": "health", "description": "Rest and grow.", "effects": {"energy": 2}},
            {"id": "eat", "label": "Eat", "category": "health", "description": "Nourish your body.", "effects": {"energy": 1, "money": -1}},
            {"id": "cry", "label": "Cry", "category": "social", "description": "Get attention from caregivers.", "effects": {"affinity": {"parent": 1}}},
        ],
        "event_tags": ["infant", "baby", "family"],
    },
    "toddler": {
        "min_age": 3,
        "max_age": 4,
        "label": "Toddler",
        "actions": [
            {"id": "play", "label": "Play", "category": "health", "description": "Explore and have fun.", "effects": {"energy": 1, "happiness": 2}},
            {"id": "learn_words", "label": "Learn words", "category": "education", "description": "Start building language skills.", "effects": {"skill": 1, "energy": -1}},
            {"id": "explore", "label": "Explore", "category": "lifestyle", "description": "Discover your surroundings.", "effects": {"happiness": 1, "energy": -1}},
        ],
        "event_tags": ["toddler", "childhood", "family"],
    },
    "child": {
        "min_age": 5,
        "max_age": 12,
        "label": "Child",
        "actions": [
            {"id": "school", "label": "School", "category": "education", "description": "Attend school and learn.", "effects": {"skill": 1, "energy": -1}},
            {"id": "play", "label": "Play", "category": "health", "description": "Have fun with friends.", "effects": {"happiness": 2, "energy": -1}},
            {"id": "hobby", "label": "Hobby", "category": "lifestyle", "description": "Develop a personal interest.", "effects": {"skill": 1, "happiness": 1}},
            {"id": "friends", "label": "Make friends", "category": "social", "description": "Build childhood friendships.", "effects": {"reputation": 1, "happiness": 1}},
        ],
        "event_tags": ["child", "school", "friendship", "family"],
    },
    "teen": {
        "min_age": 13,
        "max_age": 19,
        "label": "Teen",
        "actions": [
            {"id": "school", "label": "School", "category": "education", "description": "Continue your education.", "effects": {"skill": 1, "energy": -1}},
            {"id": "part_time", "label": "Part-time work", "category": "career", "description": "Earn money after school.", "effects": {"money": 1, "energy": -2}},
            {"id": "identity", "label": "Explore identity", "category": "lifestyle", "description": "Figure out who you are.", "effects": {"happiness": 1, "flags": {"identity_exploring": True}}},
            {"id": "romance", "label": "Romance", "category": "social", "description": "Explore first relationships.", "effects": {"happiness": 1, "reputation": 1}},
            {"id": "rebel", "label": "Rebel", "category": "lifestyle", "description": "Push against expectations.", "effects": {"reputation": -1, "happiness": 1, "flags": {"rebel_path": True}}},
        ],
        "event_tags": ["teen", "school", "identity", "romance", "rebellion"],
    },
    "young_adult": {
        "min_age": 20,
        "max_age": 34,
        "label": "Young Adult",
        "actions": [
            {"id": "career", "label": "Career", "category": "career", "description": "Work and build your path.", "effects": {"money": 1, "skill": 1, "energy": -1}},
            {"id": "romance", "label": "Romance", "category": "social", "description": "Build serious relationships.", "effects": {"happiness": 1, "reputation": 1}},
            {"id": "move", "label": "Move", "category": "lifestyle", "description": "Change your living situation.", "effects": {"money": -1, "happiness": 1}},
            {"id": "study", "label": "Study", "category": "education", "description": "Pursue higher education.", "effects": {"skill": 2, "money": -1, "energy": -1}},
            {"id": "travel", "label": "Travel", "category": "lifestyle", "description": "See the world.", "effects": {"money": -2, "happiness": 2}},
        ],
        "event_tags": ["young_adult", "career", "romance", "independence"],
    },
    "adult": {
        "min_age": 35,
        "max_age": 59,
        "label": "Adult",
        "actions": [
            {"id": "career", "label": "Career", "category": "career", "description": "Advance in your profession.", "effects": {"money": 2, "skill": 1, "energy": -1}},
            {"id": "family", "label": "Family", "category": "social", "description": "Invest in family relationships.", "effects": {"happiness": 2, "energy": -1}},
            {"id": "invest", "label": "Invest", "category": "career", "description": "Build long-term wealth.", "effects": {"money": -1, "flags": {"investing": True}}},
            {"id": "mentor", "label": "Mentor", "category": "social", "description": "Guide the next generation.", "effects": {"reputation": 2, "energy": -1}},
            {"id": "crisis", "label": "Face a crisis", "category": "lifestyle", "description": "Confront mid-life challenges.", "effects": {"happiness": -1, "flags": {"midlife_crisis": True}}},
        ],
        "event_tags": ["adult", "career", "family", "midlife"],
    },
    "senior": {
        "min_age": 60,
        "max_age": 100,
        "label": "Senior",
        "actions": [
            {"id": "retire", "label": "Retire", "category": "career", "description": "Step back from work.", "effects": {"money": 1, "happiness": 1}},
            {"id": "reflect", "label": "Reflect", "category": "lifestyle", "description": "Look back on your life.", "effects": {"happiness": 1, "skill": 1}},
            {"id": "legacy", "label": "Build legacy", "category": "social", "description": "Pass on what you've learned.", "effects": {"reputation": 2, "flags": {"legacy_building": True}}},
            {"id": "health", "label": "Health", "category": "health", "description": "Take care of your body.", "effects": {"energy": 1, "money": -1}},
            {"id": "family", "label": "Family", "category": "social", "description": "Spend time with loved ones.", "effects": {"happiness": 2}},
        ],
        "event_tags": ["senior", "retirement", "legacy", "health"],
    },
}


def get_life_stage(age: int) -> str:
    """Get the life stage key for a given age."""
    for stage_key, stage in LIFE_STAGES.items():
        if stage["min_age"] <= age <= stage["max_age"]:
            return stage_key
    return "senior" if age > 100 else "infant"


def get_life_stage_info(age: int) -> dict[str, Any]:
    """Get the full life stage definition for a given age."""
    stage_key = get_life_stage(age)
    return LIFE_STAGES[stage_key]


def get_life_stage_actions(age: int, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Get the available actions for the player's current life stage.

    Filters actions based on game state (flags, education, etc.).
    """
    stage = get_life_stage_info(age)
    actions = [dict(action) for action in stage["actions"]]

    # Filter actions based on state
    flags = state.get("flags", {})
    education = state.get("education", {})

    # School action only available if school is unlocked
    if "school" in [a["id"] for a in actions] and not education.get("school_unlocked"):
        actions = [a for a in actions if a["id"] != "school"]

    # Career action only available if player has a job or career path
    if "career" in [a["id"] for a in actions]:
        has_career = bool(state.get("career_tracks", {})) or bool(flags.get("hired"))
        if not has_career:
            actions = [a for a in actions if a["id"] != "career"]

    return actions


def get_life_stage_label(age: int) -> str:
    """Get the display label for a life stage."""
    return get_life_stage_info(age)["label"]


def get_life_stage_event_tags(age: int) -> list[str]:
    """Get the event tags associated with the current life stage."""
    return get_life_stage_info(age)["event_tags"]