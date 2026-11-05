"""Data loader for deterministic world packs.

World packs are application content, while a playthrough only stores the
selected pack id, version, and the player-specific state it produces. This
keeps the game engine small and lets a later pack add rules without changing
the core save format.
"""
from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
WORLD_PACKS_DIR = ROOT / "data" / "world_packs"


class WorldPackError(ValueError):
    """Raised when a world pack is missing or its data is malformed."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorldPackError(f"Could not read world pack file: {path.name}") from error
    if not isinstance(value, dict):
        raise WorldPackError(f"World pack file must contain an object: {path.name}")
    return value


def _require_string(value: Any, field: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldPackError(f"{source} requires a non-empty {field}.")
    return value.strip()


def _validate_pack(pack: dict[str, Any], pack_id: str) -> None:
    manifest = pack.get("manifest", {})
    if manifest.get("id") != pack_id:
        raise WorldPackError("World pack id does not match its manifest.")
    _require_string(manifest.get("name"), "name", "manifest.json")
    if not isinstance(manifest.get("version"), int):
        raise WorldPackError("manifest.json requires an integer version.")

    creation = pack.get("character_creation", {})
    for key in ("villages", "clans", "chakra_natures"):
        if not isinstance(creation.get(key), list) or not creation[key]:
            raise WorldPackError(f"character_creation.json requires a non-empty {key} list.")

    actions = pack.get("actions", {}).get("actions")
    if not isinstance(actions, list) or not actions:
        raise WorldPackError("actions.json requires a non-empty actions list.")
    seen_actions: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            raise WorldPackError("Each action must be an object.")
        action_id = _require_string(action.get("id"), "id", "actions.json")
        if action_id in seen_actions:
            raise WorldPackError(f"Duplicate world action id: {action_id}")
        seen_actions.add(action_id)
        if action.get("action_type") not in {"personal", "social"}:
            raise WorldPackError(f"Action {action_id} must use personal or social action_type.")
        if not isinstance(action.get("effects", {}), dict):
            raise WorldPackError(f"Action {action_id} effects must be an object.")

    unlocks = pack.get("progression", {}).get("unlocks")
    if not isinstance(unlocks, list):
        raise WorldPackError("progression.json requires an unlocks list.")
    progression = pack.get("progression", {})
    techniques = progression.get("techniques", [])
    if not isinstance(techniques, list):
        raise WorldPackError("progression.json techniques must be a list.")
    technique_ids = {_require_string(item.get("id"), "id", "progression.json techniques") for item in techniques if isinstance(item, dict)}
    trees = progression.get("skill_trees", [])
    if not isinstance(trees, list):
        raise WorldPackError("progression.json skill_trees must be a list.")
    tree_ids: set[str] = set()
    node_ids: set[str] = set()
    for tree in trees:
        if not isinstance(tree, dict):
            raise WorldPackError("Each skill tree must be an object.")
        tree_id = _require_string(tree.get("id"), "id", "progression.json skill tree")
        if tree_id in tree_ids:
            raise WorldPackError(f"Duplicate skill tree id: {tree_id}")
        tree_ids.add(tree_id)
        nodes = tree.get("nodes", [])
        if not isinstance(nodes, list):
            raise WorldPackError(f"Skill tree {tree_id} nodes must be a list.")
        for node in nodes:
            if not isinstance(node, dict):
                raise WorldPackError(f"Skill tree {tree_id} contains an invalid node.")
            node_id = _require_string(node.get("id"), "id", f"skill tree {tree_id}")
            if node_id in node_ids:
                raise WorldPackError(f"Duplicate skill-tree node id: {node_id}")
            node_ids.add(node_id)
            if not isinstance(node.get("requirements", {}), dict):
                raise WorldPackError(f"Skill-tree node {node_id} requirements must be an object.")
            if not isinstance(node.get("point_cost", 0), int) or node.get("point_cost", 0) < 0:
                raise WorldPackError(f"Skill-tree node {node_id} point_cost must be a non-negative integer.")
            technique_id = node.get("technique_id")
            if technique_id and technique_id not in technique_ids:
                raise WorldPackError(f"Skill-tree node {node_id} references an unknown technique.")

    shops = pack.get("shops", {})
    shop_list = shops.get("shops") if isinstance(shops, dict) else None
    if shop_list is not None:
        if not isinstance(shop_list, list) or not shop_list:
            raise WorldPackError("shops.json shops must be a non-empty list.")
        shop_ids: set[str] = set()
        for shop in shop_list:
            if not isinstance(shop, dict):
                raise WorldPackError("Each regional shop must be an object.")
            shop_id = _require_string(shop.get("id"), "id", "shops.json")
            if shop_id in shop_ids:
                raise WorldPackError(f"Duplicate regional shop id: {shop_id}")
            shop_ids.add(shop_id)
            if not isinstance(shop.get("items", []), list):
                raise WorldPackError(f"Regional shop {shop_id} items must be a list.")
            item_ids: set[str] = set()
            for item in shop.get("items", []):
                item_id = _require_string(item.get("id"), "id", f"regional shop {shop_id}")
                if item_id in item_ids:
                    raise WorldPackError(f"Duplicate item {item_id} in regional shop {shop_id}.")
                item_ids.add(item_id)
                tier = item.get("tier", 1)
                if not isinstance(tier, int) or not 1 <= tier <= 9:
                    raise WorldPackError(f"Shop item {item_id} tier must be from 1 to 9.")

    opportunities = pack.get("events", {}).get("opportunities", [])
    if not isinstance(opportunities, list):
        raise WorldPackError("events.json opportunities must be a list.")
    seen_opportunities: set[str] = set()
    for opportunity in opportunities:
        if not isinstance(opportunity, dict):
            raise WorldPackError("Each world opportunity must be an object.")
        opportunity_id = _require_string(opportunity.get("id"), "id", "events.json")
        if opportunity_id in seen_opportunities:
            raise WorldPackError(f"Duplicate world opportunity id: {opportunity_id}")
        seen_opportunities.add(opportunity_id)
        choices = opportunity.get("choices")
        if not isinstance(choices, list) or not choices:
            raise WorldPackError(f"Opportunity {opportunity_id} requires at least one choice.")
        choice_ids: set[str] = set()
        for choice in choices:
            if not isinstance(choice, dict):
                raise WorldPackError(f"Opportunity {opportunity_id} choices must be objects.")
            choice_id = _require_string(choice.get("id"), "id", "events.json")
            if choice_id in choice_ids:
                raise WorldPackError(f"Duplicate choice id in opportunity {opportunity_id}: {choice_id}")
            choice_ids.add(choice_id)
            if not isinstance(choice.get("effects", {}), dict) or not isinstance(choice.get("costs", {}), dict):
                raise WorldPackError(f"Opportunity {opportunity_id} effects and costs must be objects.")
            for cost_name, cost in choice.get("costs", {}).items():
                if cost_name not in {"personal_actions", "social_actions", "money"} or not isinstance(cost, int) or cost < 0:
                    raise WorldPackError(f"Opportunity {opportunity_id} has an invalid cost.")


def _expand_technique_series(pack: dict[str, Any]) -> None:
    """Expand compact, pack-authored technique series into normal technique records."""
    progression = pack.get("progression", {})
    series_list = progression.get("technique_series", [])
    if not isinstance(series_list, list):
        raise WorldPackError("progression.json technique_series must be a list.")
    techniques = progression.setdefault("techniques", [])
    for series in series_list:
        if not isinstance(series, dict) or not isinstance(series.get("techniques"), list):
            raise WorldPackError("Each technique series requires a techniques list.")
        defaults = series.get("defaults", {})
        if not isinstance(defaults, dict):
            raise WorldPackError("Technique series defaults must be an object.")
        for entry in series["techniques"]:
            if not isinstance(entry, dict):
                raise WorldPackError("Technique series entries must be objects.")
            techniques.append({**deepcopy(defaults), **deepcopy(entry)})


@lru_cache(maxsize=16)
def _load_world_pack(pack_id: str) -> dict[str, Any]:
    safe_id = _require_string(pack_id, "id", "world pack request").lower()
    pack_dir = WORLD_PACKS_DIR / safe_id
    manifest = _read_json(pack_dir / "manifest.json")
    files = manifest.get("files", [])
    if not isinstance(files, list):
        raise WorldPackError("manifest.json files must be a list.")

    sections: dict[str, dict[str, Any]] = {"manifest": manifest}
    for filename in files:
        if not isinstance(filename, str) or not filename.endswith(".json"):
            raise WorldPackError("manifest.json includes an invalid file name.")
        section_name = filename[:-5]
        sections[section_name] = _read_json(pack_dir / filename)

    _expand_technique_series(sections)
    _validate_pack(sections, safe_id)
    return sections


def get_world_pack(pack_id: str) -> dict[str, Any]:
    """Return a deep copy so callers cannot mutate cached content."""
    return deepcopy(_load_world_pack(pack_id))


def list_world_packs() -> list[dict[str, Any]]:
    """List valid installed packs without exposing their full content."""
    if not WORLD_PACKS_DIR.exists():
        return []
    packs: list[dict[str, Any]] = []
    for folder in sorted(WORLD_PACKS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        try:
            manifest = get_world_pack(folder.name)["manifest"]
        except WorldPackError:
            continue
        packs.append({
            "id": manifest["id"],
            "name": manifest["name"],
            "version": manifest["version"],
            "description": manifest.get("description", ""),
        })
    return packs


def get_pack_action(pack_id: str, action_id: str) -> dict[str, Any] | None:
    """Look up an action by id from a pack."""
    pack = get_world_pack(pack_id)
    return next(
        (action for action in pack["actions"]["actions"] if action.get("id") == action_id),
        None,
    )
