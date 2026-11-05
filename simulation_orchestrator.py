"""Build small, allow-listed context packets for world-pack systems."""
from __future__ import annotations

from typing import Any


def build_npc_context(state: dict[str, Any], npc: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    """Pass only the selected character's relevant state to local narration."""
    player = state.get("player", {})
    profile = player.get("naruto", {})
    world = state.get("world", {})
    location = player.get("location", "home")
    region = world.get("current_region")
    regional_conditions = world.get("region_state", {}).get(region, {})
    lore_entries = pack.get("lore", {}).get("entries", [])
    tags = {location, region, world.get("village", ""), "world"}
    lore = [
        {"title": item.get("title", ""), "summary": item.get("summary", "")[:320]}
        for item in lore_entries
        if tags.intersection(item.get("tags", []))
    ][:4]
    active_quests = [
        {"title": item.get("title", ""), "status": item.get("status", "")}
        for item in world.get("quests", [])
        if item.get("status") in {"accepted", "assigned"}
    ][:6]
    return {
        "player": {
            "name": str(player.get("name", "shinobi"))[:32],
            "age": int(player.get("age", 0)),
            "location": str(location)[:48],
            "region": str(region or "unknown")[:48],
            "village": str(world.get("village", "unknown"))[:48],
            "rank": str(world.get("rank", "Academy Student"))[:48],
            "traits": [str(item.get("name", ""))[:40] for item in profile.get("traits", [])[:8]],
            "skills": {key: int(value) for key, value in list(profile.get("skills", {}).items())[:12]},
            "chakra_nature": str(profile.get("chakra_nature", {}).get("name", "unknown"))[:32],
        },
        "npc": {
            "name": str(npc.get("name", "Village resident"))[:48],
            "role": str(npc.get("role", "resident"))[:48],
            "personality": [str(value)[:32] for value in npc.get("personality", [])[:5]],
            "affinity": max(-100, min(100, int(npc.get("affinity", 0)))),
            "trust": max(-100, min(100, int(npc.get("trust", 0)))),
            "memories": [str(value)[:180] for value in npc.get("memories", [])[-4:]],
            "recent_chat": [
                {"speaker": str(item.get("speaker", ""))[:12], "text": str(item.get("text", ""))[:240]}
                for item in npc.get("chat_history", [])[-4:]
            ],
        },
        "active_quests": active_quests,
        "regional_conditions": {
            key: max(0, min(100, int(regional_conditions.get(key, 50))))
            for key in ("security", "prosperity", "public_trust")
        },
        "lore": lore,
        "eligible_quest_templates": [
            {"id": item.get("id"), "name": item.get("name"), "type": item.get("type")}
            for item in pack.get("quests", {}).get("templates", [])
            if npc.get("role") in item.get("giver_roles", [])
            and int(player.get("age", 0)) >= int(item.get("min_age", 0))
        ][:8],
        "eligible_job_templates": [
            {"id": item.get("id"), "name": item.get("name"), "kind": item.get("kind", "Village work")}
            for item in pack.get("careers", {}).get("jobs", [])
            if npc.get("role") == "Mission Clerk"
            and int(player.get("age", 0)) >= int(item.get("min_age", 0))
            and not profile.get("career", {}).get("job_id")
            and {"Academy Student": 0, "Genin": 1, "Chunin": 2, "Jonin": 3}.get(world.get("rank", "Academy Student"), 0)
            >= {"Academy Student": 0, "Genin": 1, "Chunin": 2, "Jonin": 3}.get(item.get("min_rank", "Academy Student"), 0)
        ][:6],
    }
