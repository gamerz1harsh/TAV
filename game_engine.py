"""The UI-independent rules and save system for Riverton."""
from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from game_features import build_season_summary
from llm_service import get_dynamic_year_options
from event_director import select_event
from memory_store import add_memory as add_structured_memory, retrieve_memories, clear_memories
from npc_arcs import get_npc_arc_events, get_available_milestones
from narrative_orchestrator import build_narration_context, build_world_event_context
from game_schema import build_default_state, normalize_state, get_action_budget, get_menu_slots, get_dashboard_profile, normalize_era
from event_frameworks import resolve_framework, FrameworkError
from era_data_loader import get_era_loader
from career_system import check_career_triggers, get_available_jobs, get_career_summary
from life_stages import get_life_stage, get_life_stage_actions, get_life_stage_label
from world_system import get_world_state, apply_world_effects, get_menu_slots_with_swaps, check_world_phase
from event_queue import EventQueue
from world_pack import WorldPackError, get_pack_action, get_world_pack
from simulation_orchestrator import build_npc_context
from llm_service import generate_npc_dialogue, generate_world_event_narration
import game_config

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SAVE_FILE = DATA_DIR / "save_state.json"

# Game data loaded from data/game_config.json
SEASONS = game_config.get_seasons()
BASE_LOCATIONS = game_config.get_base_locations()
NPC_TEMPLATES = game_config.get_npc_templates()
ORIGINS = game_config.get_origins()
MAIN_EVENTS = game_config.get_main_events()
RANDOM_EVENTS = game_config.get_random_events()
LOCATIONS = dict(BASE_LOCATIONS)  # Mutable copy that can be extended with dynamic locations

NARUTO_DEFAULT_ATTRIBUTES = {
    "chakra_capacity": 12,
    "chakra_control": 4,
    "body_conditioning": 6,
    "academy_knowledge": 3,
    "hand_seals": 0,
    "willpower": 5,
    "strength": 8,
    "agility": 8,
    "intelligence": 8,
    "vitality": 8,
    "charisma": 8,
    "luck": 8,
}
NARUTO_DEFAULT_MASTERY = {"tree_walking": 0, "water_walking": 0}
NARUTO_DEFAULT_RELATIONSHIPS = {"family": 50, "academy_peers": 20, "mentors": 0}
NARUTO_DEFAULT_SKILLS = {
    "ninjutsu": 0, "taijutsu": 0, "genjutsu": 0, "shurikenjutsu": 0,
    "crafting": 0, "smithing": 0, "medicine": 0, "survival": 0,
}


class GameRuleError(ValueError):
    """Raised when the player attempts an action that game rules disallow."""


class GameEngine:
    def __init__(self, save_file: Path = SAVE_FILE) -> None:
        self.save_file = save_file
        self.state: dict[str, Any] | None = None
        self._log_callback = None
        self._game_folder: Path | None = None

    def set_log_callback(self, callback) -> None:
        """Set a callback function for logging events.
        
        The callback should accept (level, message, source) arguments.
        """
        self._log_callback = callback

    def _log(self, level: str, message: str, source: str = "GameEngine") -> None:
        """Internal logging helper that dispatches to callback if set."""
        if self._log_callback:
            self._log_callback(level, message, source)

    def _set_game_folder(self, folder: Path) -> None:
        """Set the current game folder and update save/memory paths."""
        self._game_folder = folder
        folder.mkdir(exist_ok=True)
        self.save_file = game_config.get_save_file_for_game(folder)

    def new_game(
        self,
        name: str,
        origin_id: str,
        dynamic_locations: dict[str, str] | None = None,
        dynamic_npcs: list[dict] | None = None,
        generated: dict[str, Any] | None = None,
        world_pack_id: str | None = None,
        world_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = name.strip()
        if not name:
            self._log("ERROR", "New game failed: empty name")
            raise GameRuleError("Enter a name before beginning.")
        if world_pack_id:
            return self._new_world_pack_game(name, world_pack_id, world_options or {})
        origin = next((item for item in ORIGINS if item["id"] == origin_id), None)
        if not origin:
            self._log("ERROR", f"New game failed: invalid origin '{origin_id}'")
            raise GameRuleError("Choose a valid origin.")

        # Create per-game folder: {player_name}_{timestamp}
        game_folder = game_config.create_game_folder(name)
        self._set_game_folder(game_folder)
        self._log("INFO", f"Created game folder: {game_folder.name}")

        self.state = build_default_state(name, origin, era="modern")
        self.state["npcs"] = deepcopy(NPC_TEMPLATES)
        self.state["game_folder"] = game_folder.name
        self._init_parent_state(origin_id)
        self._log("STATE", f"New game: {name} ({origin_id})")

        # Merge dynamic locations from LLM generation
        if dynamic_locations:
            self.state["dynamic_locations"] = dict(dynamic_locations)
            for loc_id, loc_desc in dynamic_locations.items():
                if loc_id not in LOCATIONS:
                    LOCATIONS[loc_id] = loc_desc.split(" - ")[0] if " - " in loc_desc else loc_desc
            self._log("INFO", f"Loaded {len(dynamic_locations)} dynamic locations")
            # Write map JSON to game folder
            map_data = {
                "center": dynamic_locations.get("center", name),
                "locations": dynamic_locations,
            }
            if generated and isinstance(generated.get("map"), dict):
                map_data = generated["map"]
            game_config.write_game_json(game_folder, game_config.MAP_FILE, map_data)

        # Merge dynamic NPCs from LLM generation
        if dynamic_npcs:
            self.state["dynamic_npcs"] = list(dynamic_npcs)
            # Add dynamic NPCs that don't conflict with existing templates
            existing_ids = {npc["id"] for npc in self.state["npcs"]}
            for npc in dynamic_npcs:
                if npc.get("id") not in existing_ids:
                    # Ensure the NPC has all required fields
                    merged_npc = {
                        "id": npc.get("id", f"npc_{len(self.state['npcs'])}"),
                        "name": npc.get("name", "Unknown"),
                        "role": npc.get("role", ""),
                        "location": npc.get("location", "apartment"),
                        "affinity": npc.get("affinity", 0),
                        "trust": npc.get("trust", 0),
                        "description": npc.get("description", ""),
                    }
                    self.state["npcs"].append(merged_npc)
                    existing_ids.add(merged_npc["id"])
            self._log("INFO", f"Loaded {len(dynamic_npcs)} dynamic NPCs")
            # Write NPC JSON to game folder
            game_config.write_game_json(game_folder, game_config.NPCS_FILE, self.state["npcs"])

        # Write character JSON
        character_data = {
            "player": self.state["player"],
            "origin": self.state["origin"],
        }
        game_config.write_game_json(game_folder, game_config.CHARACTER_FILE, character_data)

        # Write scenario JSON if generated
        if generated:
            scenario_text = generated.get("scenario", "")
            if scenario_text:
                self.state["starting_scenario"] = scenario_text
                game_config.write_game_json(game_folder, game_config.SCENARIO_FILE, {"scenario": scenario_text})
            map_data = generated.get("map", {})
            if isinstance(map_data, dict):
                self.state["starting_map"] = map_data
                game_config.write_game_json(game_folder, game_config.MAP_FILE, map_data)

        # Write events JSON (main + random events for this game)
        events_data = {
            "main_events": MAIN_EVENTS,
            "random_events": RANDOM_EVENTS,
        }
        game_config.write_game_json(game_folder, game_config.EVENTS_FILE, events_data)

        self._apply_effects(origin["effects"])
        if origin["known_npc"]:
            npc = self._npc(origin["known_npc"])
            npc["affinity"] += 2
            npc["trust"] += 1
            self._log("INFO", f"Origin bonus applied: +2 affinity, +1 trust with {origin['known_npc']}")
        self._memory(f"You arrived in Riverton as a {origin['name'].lower()}.")
        self._save()
        return self.public_state()

    def _new_world_pack_game(self, name: str, world_pack_id: str, world_options: dict[str, Any]) -> dict[str, Any]:
        """Create a deterministic world-pack game without invoking legacy content."""
        try:
            pack = get_world_pack(world_pack_id)
        except WorldPackError as error:
            self._log("ERROR", f"World pack load failed: {error}")
            raise GameRuleError(str(error)) from error

        creation = pack["character_creation"]
        village = self._pick_pack_option(creation["villages"], world_options.get("village"))
        clan = self._pick_pack_option(creation["clans"], world_options.get("clan"))
        chakra_nature = self._pick_pack_option(creation["chakra_natures"], world_options.get("chakra_nature"))
        try:
            age = int(world_options.get("age", 10))
        except (TypeError, ValueError):
            age = 10
        age = max(0, min(100, age))

        game_folder = game_config.create_game_folder(name)
        self._set_game_folder(game_folder)
        origin = {
            "id": "shinobi_candidate",
            "name": "Shinobi Candidate",
            "tag": "World pack start",
            "description": "A new life begins in a shinobi village.",
            "effects": {},
            "known_npc": None,
        }
        self.state = build_default_state(name, origin, era="modern")
        self.state["game_folder"] = game_folder.name
        self.state["npcs"] = []
        self.state["flags"] = {"world_pack": pack["manifest"]["id"]}

        player = self.state["player"]
        player["age"] = age
        player["life_stage"] = self._life_stage(age)
        player["era"] = pack["manifest"]["id"]
        player["location"] = "home"
        player["stats"] = {"energy": 5, "money": 40, "skill": 0, "reputation": 0}
        player["ui_stats"] = {"health": 72, "happiness": 58, "smarts": 48, "looks": 50}
        start_region = pack.get("regions", {}).get("start_region_by_village", {}).get(village["id"], "land_of_fire")
        traits = self._roll_birth_traits(pack, clan.get("id", ""))
        requested_nature = world_options.get("chakra_nature")
        nature_awakened = age > 5 and bool(requested_nature)
        player["naruto"] = {
            "village": {"id": village["id"], "name": village["name"]},
            "clan": {"id": clan["id"], "name": clan["name"], "lineage": deepcopy(clan.get("lineage"))},
            "chakra_nature": (
                {"id": chakra_nature["id"], "name": chakra_nature["name"]}
                if nature_awakened else {"id": "undetermined", "name": "Undetermined"}
            ),
            "nature_ceremony_complete": nature_awakened,
            "traits": traits,
            "attributes": deepcopy(NARUTO_DEFAULT_ATTRIBUTES),
            "skills": deepcopy(NARUTO_DEFAULT_SKILLS),
            "skill_xp": {key: 0 for key in NARUTO_DEFAULT_SKILLS},
            "chakra_current": NARUTO_DEFAULT_ATTRIBUTES["chakra_capacity"],
            "mastery": deepcopy(NARUTO_DEFAULT_MASTERY),
            "nature_affinity": {"wind": 0, "fire": 0, "water": 0, "earth": 0, "lightning": 0, "sand": 0, "ice": 0, "yin": 0, "yang": 0},
            "relationships": deepcopy(NARUTO_DEFAULT_RELATIONSHIPS),
            "techniques": [],
            "unlocks": [],
            "skill_points": 0,
            "skill_tree_nodes": [],
            "modes": {},
            "inventory": [],
            "equipped": {},
            "sage_mastery": 0,
        }
        self.state["npcs"] = []
        for person in pack.get("people", {}).get("people", []):
            npc = deepcopy(person)
            if npc.get("role") == "Academy peer":
                npc["age"] = age
            elif npc.get("role") == "Parent":
                npc["age"] = max(24, age + 24)
                npc["region_id"] = start_region
            elif npc.get("role") == "Academy instructor":
                npc["age"] = max(22, age + 15)
            elif npc.get("role") == "Blacksmith":
                npc["region_id"] = start_region
                npc["local_location"] = "blacksmith"
            npc["memories"] = list(npc.get("memories", []))[-20:]
            npc["interaction_counts"] = {}
            npc["reaction"] = self._npc_reaction(npc)
            self.state["npcs"].append(npc)
        self.state["world"] = {
            "era": pack["manifest"]["id"],
            "pack_id": pack["manifest"]["id"],
            "pack_version": pack["manifest"]["version"],
            "phase": "academy preparation",
            "rank": "Academy Student",
            "unlocks": {},
            "village": village["id"],
            "current_region": start_region,
            "home_region": start_region,
            "region_state": {
                region["id"]: {"security": 52, "prosperity": 48, "public_trust": 50}
                for region in pack.get("regions", {}).get("regions", [])
            },
            "encounters_seen_this_year": {},
            "influence": 0,
            "title": "Unproven",
            "quests": [],
            "chronicle": [],
            "organizations": {
                item["id"]: {"influence": 0, "level": 0}
                for item in pack.get("organizations", {}).get("organizations", [])
            },
            "active_encounter": None,
            "action_counts": {},
            "opportunities_seen": [],
            "opportunities_pending": [],
            "legacy": {"generation": 1, "generations": [], "heirs": []},
        }
        self.state["education"] = {
            "status": "academy candidate" if age < 12 else "academy student",
            "location": "academy",
            "forced": False,
            "school_unlocked": False,
        }
        self.state["parents"] = {
            "strictness": 0.5,
            "support": 0.6,
            "name": "Family",
            "style": "balanced",
            "memory": [],
        }
        self._apply_naruto_effects(clan.get("starting_effects", {}))
        for trait in traits:
            self._apply_naruto_effects(trait.get("starting_effects", {}))
        if nature_awakened:
            self._naruto_profile()["nature_affinity"][chakra_nature["id"]] = max(
                20, int(self._naruto_profile()["nature_affinity"].get(chakra_nature["id"], 0))
            )
        elif requested_nature:
            self._naruto_profile()["nature_affinity"][chakra_nature["id"]] = max(
                8, int(self._naruto_profile()["nature_affinity"].get(chakra_nature["id"], 0))
            )
        self._naruto_profile()["chakra_current"] = self._naruto_profile()["attributes"].get("chakra_capacity", 12)
        self._reset_world_action_budget()
        self._refresh_world_pack_unlocks()
        self.state["memories"] = [
            f"Age {age}: You began your shinobi life in {village['name']}."
        ]
        if age >= 5 and not nature_awakened:
            self._conduct_chakra_nature_ceremony()
            self._refresh_world_pack_unlocks()
        self._log("STATE", f"New {pack['manifest']['id']} game: {name} (age {age})")
        self._save()
        return self.public_state()

    @staticmethod
    def _pick_pack_option(options: list[dict[str, Any]], requested_id: Any) -> dict[str, Any]:
        """Select a declared pack option, falling back to its first valid entry."""
        selected = str(requested_id or "").strip().lower()
        if selected:
            for option in options:
                if option.get("id") == selected:
                    return option
        return options[0]

    @staticmethod
    def _roll_birth_traits(pack: dict[str, Any], clan_id: str = "") -> list[dict[str, Any]]:
        """Draw unique birth traits by pack-defined rarity weights."""
        remaining = [
            deepcopy(item) for item in pack.get("traits", {}).get("traits", [])
            if not item.get("requires_clan") or item.get("requires_clan") == clan_id
        ]
        count = max(1, min(4, int(pack.get("traits", {}).get("draw_count", 2))))
        selected: list[dict[str, Any]] = []
        for _ in range(min(count, len(remaining))):
            weights = [max(0.01, float(item.get("weight", 1))) for item in remaining]
            trait = random.choices(remaining, weights=weights, k=1)[0]
            selected.append(trait)
            remaining.remove(trait)
        return selected

    def _narrate_world_event(self, title: str, outcome: str, event_type: str = "encounter") -> str:
        """Ask the local model for brief flavor after deterministic rules resolve."""
        context = build_world_event_context(self.state, title, outcome, event_type)
        return generate_world_event_narration(context) or outcome[:240]

    def _conduct_chakra_nature_ceremony(self) -> dict[str, Any] | None:
        """Resolve the age-five nature ceremony from affinity-weighted base natures."""
        profile = self._naruto_profile()
        if profile.get("nature_ceremony_complete"):
            return None
        pack = self._active_world_pack()
        natures = pack.get("character_creation", {}).get("chakra_natures", [])
        if not natures:
            return None
        affinity = profile.setdefault("nature_affinity", {})
        weights = [
            max(0.01, float(item.get("weight", 1)))
            * (1 + max(0, int(affinity.get(item.get("id"), 0))))
            for item in natures
        ]
        nature = random.choices(natures, weights=weights, k=1)[0]
        profile["chakra_nature"] = {"id": nature["id"], "name": nature["name"]}
        profile["nature_ceremony_complete"] = True
        affinity[nature["id"]] = max(20, int(affinity.get(nature["id"], 0)) + 20)
        event = {
            "title": "The Age-Five Chakra Ceremony",
            "nature": nature["name"],
            "year": int(self.state.get("year", 1)),
        }
        self.state.setdefault("world", {})["nature_ceremony"] = event
        memory = f"At the age-five chakra ceremony, your natural affinity was revealed as {nature['name']}."
        self._record_world_memory(f"Age 5: {memory}")
        self.state["world"]["last_narration"] = self._narrate_world_event(
            event["title"], f"{memory} The ceremony confirmed your affinity and opened its training path.", "ceremony"
        )
        return event

    def _maybe_trigger_world_disaster(self) -> dict[str, Any] | None:
        """Roll at most one pack-authored disaster check in a world year."""
        pack = self._active_world_pack()
        event_data = pack.get("events", {})
        disasters = event_data.get("disasters", [])
        world = self.state.setdefault("world", {})
        year = int(self.state.get("year", 1))
        if not disasters or world.get("active_encounter") or world.get("disaster_year") == year:
            return None
        world["disaster_year"] = year
        risk = max(0.0, min(0.75, float(event_data.get("disaster_chance", 0.12))))
        traits = self._naruto_profile().get("traits", [])
        resistance = sum(float(item.get("modifiers", {}).get("disaster_resistance_percent", 0)) for item in traits)
        risk *= max(0.0, 1 - resistance / 100)
        if random.random() >= risk:
            return None
        region_id = world.get("current_region")
        eligible = [item for item in disasters if not item.get("regions") or region_id in item.get("regions", [])]
        if not eligible:
            return None
        disaster = deepcopy(random.choice(eligible))
        encounter = {
            "id": disaster.get("id"),
            "type": "disaster",
            "region_id": region_id,
            "title": disaster.get("title", "A crisis unfolds"),
            "description": disaster.get("description", "A sudden event puts the community at risk."),
            "choices": disaster.get("choices", []),
        }
        encounter["description"] = self._narrate_world_event(
            encounter["title"], encounter["description"], "disaster"
        )
        world["active_encounter"] = encounter
        return encounter

    def _is_world_pack_game(self) -> bool:
        return bool(self.state and isinstance(self.state.get("world"), dict) and self.state["world"].get("pack_id"))

    def _active_world_pack(self) -> dict[str, Any]:
        self._require_state()
        pack_id = self.state.get("world", {}).get("pack_id")
        if not pack_id:
            raise GameRuleError("This save is not using a world pack.")
        try:
            return get_world_pack(str(pack_id))
        except WorldPackError as error:
            raise GameRuleError(str(error)) from error

    def _world_places(self, pack: dict[str, Any]) -> list[dict[str, Any]]:
        """Return facilities for the current country and fixed regional landmarks."""
        world = self.state.get("world", {})
        current_region = world.get("current_region")
        region = next((item for item in pack.get("regions", {}).get("regions", []) if item.get("id") == current_region), {})
        village_name = region.get("village", "Village")
        places = []
        for source in pack.get("people", {}).get("places", []):
            if source.get("map_visible") is False:
                continue
            place = deepcopy(source)
            if place.get("local_facility"):
                place["region_id"] = world.get("home_region", current_region) if place.get("id") == "home" else current_region
                if current_region != "land_of_fire":
                    place["name"] = {
                        "home": "Family Home",
                        "academy": f"{village_name} Academy",
                        "training_ground": f"{village_name} Training Grounds",
                        "market_street": f"{village_name} Market",
                        "blacksmith": f"{village_name} Forge",
                        "clinic": f"{village_name} Clinic",
                        "hokage_tower": f"{village_name} Administration",
                    }.get(place.get("id"), place.get("name", "Village place"))
            places.append(place)
        return places

    def _world_person_location(self, person: dict[str, Any]) -> str:
        region_id = person.get("region_id")
        if region_id and region_id == self.state.get("world", {}).get("current_region"):
            return str(person.get("local_location") or person.get("location", "unknown"))
        return str(person.get("location", "unknown"))

    def _world_person_is_here(self, person: dict[str, Any], location_id: str | None = None) -> bool:
        expected = location_id if location_id is not None else self.state.get("player", {}).get("location")
        return self._world_person_location(person) == expected

    def _world_people(self) -> list[dict[str, Any]]:
        people = []
        for person in self.state.get("npcs", []):
            item = deepcopy(person)
            item["location"] = self._world_person_location(person)
            people.append(item)
        return people

    def _naruto_profile(self) -> dict[str, Any]:
        """Return the player profile for the current shinobi pack and migrate old saves."""
        self._require_state()
        profile = self.state.setdefault("player", {}).setdefault("naruto", {})
        profile.setdefault("attributes", deepcopy(NARUTO_DEFAULT_ATTRIBUTES))
        profile.setdefault("skills", deepcopy(NARUTO_DEFAULT_SKILLS))
        profile.setdefault("skill_xp", {key: 0 for key in NARUTO_DEFAULT_SKILLS})
        profile.setdefault("mastery", deepcopy(NARUTO_DEFAULT_MASTERY))
        profile.setdefault("nature_affinity", {"wind": 0, "fire": 0, "water": 0, "earth": 0, "lightning": 0, "sand": 0, "ice": 0, "yin": 0, "yang": 0})
        profile.setdefault("relationships", deepcopy(NARUTO_DEFAULT_RELATIONSHIPS))
        profile.setdefault("techniques", [])
        profile.setdefault("unlocks", [])
        profile.setdefault("traits", [])
        profile.setdefault("skill_points", 0)
        profile.setdefault("skill_tree_nodes", [])
        profile.setdefault("modes", {})
        profile.setdefault("inventory", [])
        profile.setdefault("equipped", {})
        profile.setdefault("sage_mastery", 0)
        profile.setdefault("nature_ceremony_complete", profile.get("chakra_nature", {}).get("id") != "undetermined")
        profile.setdefault("chakra_current", int(profile.get("attributes", {}).get("chakra_capacity", 12)))
        for index, item in enumerate(profile.get("inventory", [])):
            if isinstance(item, dict):
                item.setdefault("instance_id", f"{item.get('id', 'item')}:legacy:{index + 1}")
                item.setdefault("quantity", 1)
        for key, value in NARUTO_DEFAULT_ATTRIBUTES.items():
            profile["attributes"].setdefault(key, value)
        for key, value in NARUTO_DEFAULT_SKILLS.items():
            profile["skills"].setdefault(key, value)
            profile["skill_xp"].setdefault(key, value * 10)
        for key, value in NARUTO_DEFAULT_MASTERY.items():
            profile["mastery"].setdefault(key, value)
        for key, value in NARUTO_DEFAULT_RELATIONSHIPS.items():
            profile["relationships"].setdefault(key, value)
        for key in ("wind", "fire", "water", "earth", "lightning", "sand", "ice", "yin", "yang"):
            profile["nature_affinity"].setdefault(key, 0)
        for technique in profile.get("techniques", []):
            if isinstance(technique, dict):
                technique.setdefault("base_tier", max(1, int(technique.get("tier", 1))))
                technique.setdefault("tier", technique["base_tier"])
        return profile

    def _combat_power(self, profile: dict[str, Any]) -> int:
        attributes = self._effective_attributes(profile)
        skills = self._effective_skills(profile)
        techniques = profile.get("techniques", [])
        base = max(0, int(
            sum(int(attributes.get(key, 0)) for key in ("strength", "agility", "vitality", "chakra_control", "chakra_capacity"))
            + sum(int(skills.get(key, 0)) for key in ("ninjutsu", "taijutsu", "genjutsu", "shurikenjutsu"))
            + sum(int(item.get("combat_power", 0)) + int(item.get("level", 1)) * int(item.get("power_per_level", 0))
                  for item in techniques if item.get("type", "active") == "passive" and item.get("active", True))
            + sum(max(0, int(item.get("tier", 1)) - 1) * int(item.get("power_per_tier", 2)) for item in techniques)
            + sum(int(item.get("mastery", 0)) for item in techniques) // 5
        ))
        gear_power = 0
        equipped = profile.get("equipped", {})
        inventory = profile.get("inventory", [])
        for item_id in equipped.values():
            item = next((entry for entry in inventory if entry.get("instance_id") == item_id), None)
            if item:
                gear_power += int(item.get("combat_power_per_tier", item.get("combat_power", 0))) * int(item.get("tier", 1))
        mode_power = sum(
            int(mode.get("combat_power", 0))
            + max(0, int(mode.get("tier", 1)) - 1) * int(mode.get("combat_power_per_tier", 4))
            for mode in profile.get("modes", {}).values() if mode.get("active")
        )
        power = base + gear_power + mode_power
        power_bonus = sum(float(item.get("modifiers", {}).get("combat_power_percent", 0)) for item in profile.get("traits", []))
        return max(0, int(round(power * max(0, 100 + power_bonus) / 100)))

    def _effective_skills(self, profile: dict[str, Any] | None = None) -> dict[str, int]:
        """Include skill bonuses from the current equipment loadout."""
        profile = profile or self._naruto_profile()
        result = {key: int(value) for key, value in profile.get("skills", {}).items()}
        for item_id in profile.get("equipped", {}).values():
            item = next((entry for entry in profile.get("inventory", []) if entry.get("instance_id") == item_id), None)
            if not item:
                continue
            tier = max(1, min(9, int(item.get("tier", 1))))
            for key, amount in item.get("skill_modifiers_per_tier", {}).items():
                result[key] = result.get(key, 0) + int(amount) * tier
        return result

    def _effective_attributes(self, profile: dict[str, Any] | None = None) -> dict[str, int]:
        """Return base attributes plus equipped gear, passive techniques, and active modes."""
        profile = profile or self._naruto_profile()
        result = {key: int(value) for key, value in profile.get("attributes", {}).items()}
        for technique in profile.get("techniques", []):
            passive = technique.get("type", "active") == "passive"
            if passive and not technique.get("active", True):
                continue
            level_scale = max(0, int(technique.get("level", 1)) - 1)
            per_level = technique.get("stat_per_level", {})
            if passive:
                for key, amount in technique.get("stat_modifiers", {}).items():
                    result[key] = result.get(key, 0) + int(amount)
            if not per_level and level_scale:
                skill = str(technique.get("nature", "")).lower()
                stat = "agility" if "taijutsu" in skill else "chakra_control" if "ninjutsu" in skill else "intelligence"
                per_level = {stat: 1}
            for key, amount in per_level.items():
                result[key] = result.get(key, 0) + int(amount) * level_scale
            tier_bonus = technique.get("stat_per_tier", {})
            if not tier_bonus and int(technique.get("tier", 1)) > 1:
                tier_bonus = {"agility" if "taijutsu" in str(technique.get("nature", "")).lower() else "chakra_control": 1}
            for key, amount in tier_bonus.items():
                result[key] = result.get(key, 0) + int(amount) * max(0, int(technique.get("tier", 1)) - 1)
        for slot, item_id in profile.get("equipped", {}).items():
            item = next((entry for entry in profile.get("inventory", []) if entry.get("instance_id") == item_id), None)
            if not item:
                continue
            tier = max(1, min(9, int(item.get("tier", 1))))
            for key, amount in item.get("modifiers_per_tier", item.get("modifiers", {})).items():
                result[key] = result.get(key, 0) + int(amount) * tier
        for mode in profile.get("modes", {}).values():
            if not mode.get("active"):
                continue
            for key, amount in mode.get("bonuses", {}).items():
                result[key] = result.get(key, 0) + int(amount)
            for key, amount in mode.get("stat_per_tier", {}).items():
                result[key] = result.get(key, 0) + int(amount) * max(0, int(mode.get("tier", 1)) - 1)
            per_100 = mode.get("mastery_bonus_per_100", {})
            mastery_scale = int(mode.get("mastery", 0)) // 100
            for key, amount in per_100.items():
                result[key] = result.get(key, 0) + int(amount) * mastery_scale
        return result

    @staticmethod
    def _nature_matchup(player_nature: str, opponent_nature: str) -> int:
        """Return a nature edge including a few pack-defined advanced counters."""
        player_nature, opponent_nature = player_nature.lower(), opponent_nature.lower()
        if not player_nature or not opponent_nature or player_nature == opponent_nature:
            return 0
        edges = {
            ("fire", "wind"), ("wind", "lightning"), ("lightning", "earth"),
            ("earth", "water"), ("water", "fire"), ("fire", "ice"),
            ("ice", "water"), ("water", "sand"),
        }
        if (player_nature, opponent_nature) in edges:
            return 1
        if (opponent_nature, player_nature) in edges:
            return -1
        return 0

    @staticmethod
    def _combat_win_probability(player_power: int, opponent_power: int, nature_edge: int = 0) -> float:
        """Estimate a bounded win chance; actual combat still resolves by rolls and choices."""
        scale = max(30, player_power + opponent_power + 20)
        estimate = 50 + (player_power - opponent_power) / scale * 85 + nature_edge * 9
        return round(max(5, min(95, estimate)), 1)

    def _record_world_memory(self, text: str) -> None:
        memories = self.state.setdefault("memories", [])
        memories.append(text)
        self.state["memories"] = memories[-40:]

    def _apply_naruto_effects(self, effects: dict[str, Any]) -> None:
        """Apply a declared pack effect. The engine clamps every mutable value."""
        if not effects:
            return
        if isinstance(effects.get("money"), (int, float)):
            wallet = self.state["player"].setdefault("stats", {})
            money_delta = int(effects["money"])
            if money_delta > 0:
                income_bonus = sum(float(item.get("modifiers", {}).get("income_percent", 0)) for item in self._naruto_profile().get("traits", []))
                money_delta += max(0, int(money_delta * income_bonus / 100))
            wallet["money"] = max(0, int(wallet.get("money", 0)) + money_delta)
        profile = self._naruto_profile()
        targets = {
            "attributes": profile["attributes"],
            "mastery": profile["mastery"],
            "nature_affinity": profile["nature_affinity"],
            "relationships": profile["relationships"],
            "ui_stats": self.state["player"].setdefault("ui_stats", {}),
        }
        for section, target in targets.items():
            changes = effects.get(section, {})
            if not isinstance(changes, dict):
                continue
            for key, delta in changes.items():
                if not isinstance(delta, (int, float)):
                    continue
                current = target.get(key, 50 if section == "ui_stats" else 0)
                target[key] = max(0, min(100, int(current + delta)))
        if isinstance(effects.get("skill_points"), (int, float)):
            profile["skill_points"] = max(0, int(profile.get("skill_points", 0)) + int(effects["skill_points"]))
        for skill, amount in effects.get("skill_xp", {}).items():
            if skill not in NARUTO_DEFAULT_SKILLS or not isinstance(amount, (int, float)):
                continue
            bonus_percent = sum(
                int(trait.get("modifiers", {}).get(f"{skill}_xp_percent", 0))
                + int(trait.get("modifiers", {}).get("all_xp_percent", 0))
                + int(trait.get("modifiers", {}).get("training_xp_percent", 0))
                for trait in profile.get("traits", [])
            )
            gain = max(0, int(amount))
            if bonus_percent:
                gain += max(0, int(gain * bonus_percent / 100))
            xp = profile["skill_xp"].get(skill, 0) + gain
            profile["skill_xp"][skill] = xp
            profile["skills"][skill] = min(100, xp // 10)
        capacity = int(profile["attributes"].get("chakra_capacity", 0))
        profile["chakra_current"] = min(capacity, int(profile.get("chakra_current", capacity)))
        technique_id = effects.get("learn_technique")
        if isinstance(technique_id, str):
            known = {item.get("id") for item in profile.get("techniques", [])}
            pack = self._active_world_pack()
            technique = next(
                (item for item in pack.get("progression", {}).get("techniques", []) if item.get("id") == technique_id),
                None,
            )
            if technique and technique_id not in known:
                learned = deepcopy(technique)
                learned["mastery"] = 0
                learned["level"] = 1
                learned["xp"] = 0
                learned["base_tier"] = max(1, min(9, int(learned.get("tier", 1))))
                learned["tier"] = learned["base_tier"]
                learned["max_level"] = max(1, int(learned.get("max_level", 18)))
                learned["xp_per_level"] = max(1, int(learned.get("xp_per_level", 20)))
                learned["active"] = learned.get("type", "active") == "passive"
                profile["techniques"].append(learned)
        technique_practice = effects.get("practice_technique")
        if technique_practice and profile.get("techniques"):
            if isinstance(technique_practice, dict):
                target_id = technique_practice.get("technique_id")
                mastery_gain = int(technique_practice.get("mastery", 4))
            else:
                target_id = None
                mastery_gain = int(technique_practice) if isinstance(technique_practice, int) else 4
            chosen = next(
                (item for item in profile["techniques"] if item.get("id") == target_id),
                profile["techniques"][0],
            )
            gain = max(1, mastery_gain)
            max_level = max(1, int(chosen.get("max_level", 10)))
            xp_per_level = max(1, int(chosen.get("xp_per_level", 20)))
            chosen["xp"] = min(max_level * xp_per_level, max(0, int(chosen.get("xp", 0))) + gain)
            chosen["level"] = min(max_level, 1 + int(chosen["xp"]) // xp_per_level)
            trained_tier = min(9, 1 + int((chosen["level"] - 1) * 8 / max(1, max_level - 1)))
            chosen["tier"] = max(int(chosen.get("base_tier", 1)), trained_tier)
            chosen["mastery"] = min(100, int(chosen.get("mastery", 0)) + gain)
        sage_practice = effects.get("practice_sage_mode")
        if isinstance(sage_practice, dict):
            mode_id = sage_practice.get("mode_id")
            mode = profile.get("modes", {}).get(mode_id)
            if mode:
                mode["mastery"] = min(1000, int(mode.get("mastery", 0)) + max(1, int(sage_practice.get("mastery", 10))))
                mode["tier"] = min(9, 1 + int(mode["mastery"]) // 100)
                profile["sage_mastery"] = int(mode["mastery"])
        rank = effects.get("rank")
        if isinstance(rank, str) and rank.strip():
            self.state.setdefault("world", {})["rank"] = rank.strip()

    def _apply_world_effects(self, effects: dict[str, Any]) -> None:
        """Apply trusted pack effects that can influence shared world state."""
        if not isinstance(effects, dict):
            return
        self._apply_naruto_effects(effects)
        world = self.state.setdefault("world", {})
        if isinstance(effects.get("world_influence"), (int, float)):
            world["influence"] = max(0, min(1000, int(world.get("influence", 0)) + int(effects["world_influence"])))
            influence = int(world["influence"])
            world["title"] = "Village Asset" if influence >= 20 else "Reliable Shinobi" if influence >= 8 else "Known Face" if influence >= 3 else "Unproven"
        organization_effects = effects.get("organizations", {})
        if not isinstance(organization_effects, dict):
            organization_effects = {}
        for organization_id, delta in organization_effects.items():
            organization = world.setdefault("organizations", {}).setdefault(organization_id, {"influence": 0, "level": 0})
            if isinstance(delta, (int, float)):
                organization["influence"] = max(0, min(1000, int(organization.get("influence", 0)) + int(delta)))
                organization["level"] = min(3, int(organization["influence"]) // 5)
        regional_effects = effects.get("regional_effects", {})
        if isinstance(regional_effects, dict):
            region_state = world.setdefault("region_state", {})
            known_regions = {item.get("id") for item in self._active_world_pack().get("regions", {}).get("regions", [])}
            for region_id, changes in regional_effects.items():
                if region_id not in known_regions or not isinstance(changes, dict):
                    continue
                target = region_state.setdefault(region_id, {"security": 50, "prosperity": 50, "public_trust": 50})
                for key in ("security", "prosperity", "public_trust"):
                    delta = changes.get(key)
                    if isinstance(delta, (int, float)):
                        target[key] = max(0, min(100, int(target.get(key, 50)) + int(delta)))
        memory = effects.get("memory")
        if isinstance(memory, str) and memory:
            world.setdefault("chronicle", []).append({"year": int(self.state.get("year", 1)), "text": memory[:240]})
            world["chronicle"] = world["chronicle"][-80:]

    def _world_requirement_reason(self, requirements: dict[str, Any]) -> str | None:
        profile = self._naruto_profile()
        age = int(self.state.get("player", {}).get("age", 0))
        required_age = requirements.get("age")
        if isinstance(required_age, int) and age < required_age:
            return f"Available at age {required_age}."
        if requirements.get("nature_ceremony_complete") and not profile.get("nature_ceremony_complete", False):
            return "The age-five chakra ceremony has not revealed your nature yet."
        required_location = requirements.get("location")
        if isinstance(required_location, str) and self.state.get("player", {}).get("location") != required_location:
            return f"Go to {required_location.replace('_', ' ').title()} first."
        for section in ("attributes", "skills", "mastery", "nature_affinity"):
            requested = requirements.get(section, {})
            if not isinstance(requested, dict):
                continue
            values = profile.get(section, {})
            for key, needed in requested.items():
                if isinstance(needed, (int, float)) and values.get(key, 0) < needed:
                    label = key.replace("_", " ").title()
                    return f"Needs {label} {int(needed)}."
        sage_mastery = requirements.get("sage_mastery")
        if isinstance(sage_mastery, (int, float)) and int(profile.get("sage_mastery", 0)) < sage_mastery:
            return f"Needs Sage Mode mastery {int(sage_mastery)}."
        nature = requirements.get("chakra_nature")
        if isinstance(nature, str) and not profile.get("nature_ceremony_complete", True):
            return "The age-five chakra ceremony has not revealed your nature yet."
        if isinstance(nature, str) and profile.get("chakra_nature", {}).get("id") != nature:
            return f"Requires {nature.title()} chakra nature."
        chakra_natures = requirements.get("chakra_natures")
        if isinstance(chakra_natures, list) and profile.get("chakra_nature", {}).get("id") not in chakra_natures:
            return "Requires one of these natures: " + ", ".join(str(item).title() for item in chakra_natures) + "."
        clan = requirements.get("clan")
        if isinstance(clan, str) and profile.get("clan", {}).get("id") != clan:
            return f"Requires the {clan.title()} clan."
        rank = requirements.get("rank")
        if isinstance(rank, str) and self.state.get("world", {}).get("rank") != rank:
            return f"Requires {rank} rank."
        rank_order = {"Academy Student": 0, "Genin": 1, "Chunin": 2, "Jonin": 3, "Kage": 4}
        minimum_rank = requirements.get("rank_at_least")
        current_rank = str(self.state.get("world", {}).get("rank", "Academy Student"))
        if isinstance(minimum_rank, str) and rank_order.get(current_rank, 0) < rank_order.get(minimum_rank, 99):
            return f"Requires {minimum_rank} rank or higher."
        world_influence = requirements.get("world_influence_min")
        if isinstance(world_influence, (int, float)) and int(self.state.get("world", {}).get("influence", 0)) < world_influence:
            return f"Needs {int(world_influence)} village influence."
        combat_power = requirements.get("combat_power_min")
        if isinstance(combat_power, (int, float)) and self._combat_power(profile) < combat_power:
            return f"Needs power level {int(combat_power)}."
        money = requirements.get("money_min")
        if isinstance(money, (int, float)) and int(self.state.get("player", {}).get("stats", {}).get("money", 0)) < money:
            return f"Needs {int(money)} Ryo."
        requested_relationships = requirements.get("relationships", {})
        if isinstance(requested_relationships, dict):
            for key, needed in requested_relationships.items():
                if isinstance(needed, (int, float)) and profile.get("relationships", {}).get(key, 0) < needed:
                    return f"Needs {key.replace('_', ' ').title()} bond {int(needed)}."
        for unlock_id in requirements.get("unlocks", []):
            if not self.state.get("world", {}).get("unlocks", {}).get(unlock_id):
                return "Complete the preceding control training first."
        owned_nodes = set(profile.get("skill_tree_nodes", []))
        for node_id in requirements.get("nodes", []):
            if node_id not in owned_nodes:
                return f"Unlock {str(node_id).replace('_', ' ').title()} first."
        technique_count = requirements.get("technique_count")
        if isinstance(technique_count, int) and len(profile.get("techniques", [])) < technique_count:
            return "Requires a learned technique."
        return None

    def _world_skill_trees_state(self) -> list[dict[str, Any]]:
        """Expose only trees and clan branches supported by the selected pack and character."""
        pack = self._active_world_pack()
        profile = self._naruto_profile()
        owned = set(profile.get("skill_tree_nodes", []))
        trees = []
        for tree in pack.get("progression", {}).get("skill_trees", []):
            nodes = []
            for source in tree.get("nodes", []):
                requirements = source.get("requirements", {})
                required_clan = requirements.get("clan") if isinstance(requirements, dict) else None
                if required_clan and required_clan != profile.get("clan", {}).get("id"):
                    continue
                node = deepcopy(source)
                node.pop("effects", None)
                node.pop("mode", None)
                node.pop("mode_upgrade", None)
                node.pop("technique_id", None)
                node["unlocked"] = node.get("id") in owned
                node["available"] = False
                node["lock_reason"] = None if node["unlocked"] else self._world_requirement_reason(requirements)
                if not node["unlocked"] and node["lock_reason"] is None:
                    point_cost = max(0, int(source.get("point_cost", 0)))
                    if int(profile.get("skill_points", 0)) < point_cost:
                        node["lock_reason"] = f"Needs {point_cost} skill points."
                    elif int(self.state.get("personal_actions_remaining", 0)) <= 0:
                        node["lock_reason"] = "No personal actions remain this year."
                    else:
                        node["available"] = True
                nodes.append(node)
            if nodes:
                trees.append({"id": tree.get("id"), "name": tree.get("name"), "description": tree.get("description", ""), "nodes": nodes})
        return trees

    def learn_world_skill_node(self, node_id: str) -> dict[str, Any]:
        """Spend a personal action and earned skill points on an eligible pack node."""
        self._require_state()
        pack = self._active_world_pack()
        profile = self._naruto_profile()
        node = next((node for tree in pack.get("progression", {}).get("skill_trees", []) for node in tree.get("nodes", []) if node.get("id") == node_id), None)
        if node is None:
            raise GameRuleError("That skill-tree node is not in this world pack.")
        if node_id in profile.get("skill_tree_nodes", []):
            raise GameRuleError("That skill is already unlocked.")
        reason = self._world_requirement_reason(node.get("requirements", {}))
        if reason:
            raise GameRuleError(reason)
        cost = max(0, int(node.get("point_cost", 0)))
        if int(profile.get("skill_points", 0)) < cost:
            raise GameRuleError(f"You need {cost} skill points to learn this path.")
        if int(self.state.get("personal_actions_remaining", 0)) <= 0:
            raise GameRuleError("No personal actions remain this year.")
        profile["skill_points"] -= cost
        profile.setdefault("skill_tree_nodes", []).append(node_id)
        self._apply_naruto_effects(node.get("effects", {}))
        technique_id = node.get("technique_id")
        if technique_id:
            self._apply_naruto_effects({"learn_technique": technique_id})
        for unlock_id in node.get("unlocks", []):
            self.state.setdefault("world", {}).setdefault("unlocks", {})[unlock_id] = True
        mode = node.get("mode")
        if isinstance(mode, dict):
            mode_id = str(mode.get("id", node_id))
            profile.setdefault("modes", {})[mode_id] = {
                **deepcopy(mode), "active": False, "tier": max(1, int(mode.get("tier", 1))),
                "mastery": int(mode.get("starting_mastery", 0)),
            }
        upgrade = node.get("mode_upgrade")
        if isinstance(upgrade, dict):
            mode = profile.setdefault("modes", {}).get(upgrade.get("mode_id"))
            if not mode:
                raise GameRuleError("The base mode must be unlocked before its advanced form.")
            mode["variant"] = upgrade.get("variant", node_id)
            mode["tier"] = max(int(mode.get("tier", 1)), min(9, int(upgrade.get("tier", mode.get("tier", 1)))))
            mode["bonuses"] = {key: int(value) + int(mode.get("bonuses", {}).get(key, 0)) for key, value in upgrade.get("bonuses", {}).items()}
            mode["combat_power"] = int(mode.get("combat_power", 0)) + int(upgrade.get("combat_power", 0))
        self.state["personal_actions_remaining"] -= 1
        self.state["actions_remaining"] = self.state.get("personal_actions_remaining", 0) + self.state.get("social_actions_remaining", 0)
        self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: You unlocked {node.get('name', node_id)}.")
        self._refresh_world_pack_unlocks()
        self._save()
        return self.public_state()

    def toggle_world_mode(self, mode_id: str, active: bool) -> dict[str, Any]:
        """Activate one unlocked transformation or Sage mode, or switch it off."""
        self._require_state()
        profile = self._naruto_profile()
        mode = profile.get("modes", {}).get(mode_id)
        if not mode:
            raise GameRuleError("That mode has not been unlocked.")
        if active:
            cost = max(0, int(mode.get("chakra_cost", 0)))
            if int(profile.get("chakra_current", 0)) < cost:
                raise GameRuleError(f"You need {cost} chakra to activate {mode.get('name', 'this mode')}.")
            profile["chakra_current"] -= cost
            for other in profile["modes"].values():
                other["active"] = False
        mode["active"] = bool(active)
        self._save()
        return self.public_state()

    def toggle_passive_technique(self, technique_id: str, active: bool) -> dict[str, Any]:
        self._require_state()
        technique = next((item for item in self._naruto_profile().get("techniques", []) if item.get("id") == technique_id), None)
        if not technique or technique.get("type", "active") != "passive":
            raise GameRuleError("Only a learned passive technique can be toggled.")
        technique["active"] = bool(active)
        self._save()
        return self.public_state()

    def _refresh_world_pack_unlocks(self) -> list[str]:
        """Unlock progression nodes once deterministic requirements are met."""
        if not self._is_world_pack_game():
            return []
        pack = self._active_world_pack()
        world_unlocks = self.state.setdefault("world", {}).setdefault("unlocks", {})
        newly_unlocked: list[str] = []
        for unlock in pack["progression"].get("unlocks", []):
            unlock_id = unlock.get("id")
            if not isinstance(unlock_id, str) or world_unlocks.get(unlock_id):
                continue
            if self._world_requirement_reason(unlock.get("requirements", {})) is None:
                world_unlocks[unlock_id] = True
                newly_unlocked.append(unlock_id)
        profile = self._naruto_profile()
        profile["unlocks"] = sorted(key for key, enabled in world_unlocks.items() if enabled)
        return newly_unlocked

    def _refresh_world_opportunities(self) -> list[str]:
        """Queue at most one newly-earned pack opportunity at a time."""
        if not self._is_world_pack_game():
            return []
        world = self.state.setdefault("world", {})
        pending = world.setdefault("opportunities_pending", [])
        seen = set(world.setdefault("opportunities_seen", []))
        if pending or world.get("active_encounter"):
            return []
        for opportunity in self._active_world_pack().get("events", {}).get("opportunities", []):
            opportunity_id = opportunity.get("id")
            if not isinstance(opportunity_id, str) or opportunity_id in seen:
                continue
            requirements = opportunity.get("requirements", {})
            if not self._world_opportunity_requirements_met(requirements):
                continue
            choices = [
                {
                    "id": item.get("id"),
                    "label": item.get("label", "Choose"),
                    "description": item.get("description", ""),
                    "costs": deepcopy(item.get("costs", {})),
                }
                for item in opportunity.get("choices", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
            if not choices:
                continue
            pending.append({
                "id": opportunity_id,
                "title": str(opportunity.get("title", "An opportunity"))[:100],
                "description": str(opportunity.get("description", "A new possibility has appeared."))[:500],
                "triggered_year": int(self.state.get("year", 1)),
                "choices": choices,
            })
            seen.add(opportunity_id)
            world["opportunities_seen"] = sorted(seen)
            return [opportunity_id]
        return []

    def _world_opportunity_requirements_met(self, requirements: dict[str, Any]) -> bool:
        if not isinstance(requirements, dict):
            return False
        player = self.state.get("player", {})
        profile = self._naruto_profile()
        world = self.state.get("world", {})
        if int(player.get("age", 0)) < int(requirements.get("min_age", 0)):
            return False
        if requirements.get("location") and player.get("location") != requirements["location"]:
            return False
        if requirements.get("current_region") and world.get("current_region") != requirements["current_region"]:
            return False
        if requirements.get("clan") and profile.get("clan", {}).get("id") != requirements["clan"]:
            return False
        if int(world.get("influence", 0)) < int(requirements.get("min_world_influence", 0)):
            return False
        for action_id, count in requirements.get("action_counts", {}).items():
            if int(world.get("action_counts", {}).get(action_id, 0)) < int(count):
                return False
        for npc_id, trust in requirements.get("npc_trust", {}).items():
            npc = next((item for item in self.state.get("npcs", []) if item.get("id") == npc_id), None)
            if npc is None or int(npc.get("trust", 0)) < int(trust):
                return False
        region_requirements = requirements.get("min_region_state", {})
        region_values = world.get("region_state", {}).get(world.get("current_region"), {})
        if any(int(region_values.get(key, 0)) < int(value) for key, value in region_requirements.items()):
            return False
        if requirements.get("no_active_encounter") and world.get("active_encounter"):
            return False
        return True

    def resolve_world_opportunity(self, opportunity_id: str, choice_id: str) -> dict[str, Any]:
        """Resolve a pending event using only effects authored by the active pack."""
        self._require_state()
        pack = self._active_world_pack()
        event = next((item for item in pack.get("events", {}).get("opportunities", []) if item.get("id") == opportunity_id), None)
        pending = self.state.setdefault("world", {}).setdefault("opportunities_pending", [])
        queued = next((item for item in pending if item.get("id") == opportunity_id), None)
        if event is None or queued is None:
            raise GameRuleError("That opportunity is no longer waiting for a decision.")
        choice = next((item for item in event.get("choices", []) if item.get("id") == choice_id), None)
        if choice is None:
            raise GameRuleError("That choice is not part of this opportunity.")
        costs = choice.get("costs", {})
        personal_cost = max(0, int(costs.get("personal_actions", 0)))
        social_cost = max(0, int(costs.get("social_actions", 0)))
        money_cost = max(0, int(costs.get("money", 0)))
        if self.state.get("personal_actions_remaining", 0) < personal_cost:
            raise GameRuleError("You do not have enough personal actions for that choice.")
        if self.state.get("social_actions_remaining", 0) < social_cost:
            raise GameRuleError("You do not have enough social actions for that choice.")
        wallet = self.state["player"].setdefault("stats", {})
        if int(wallet.get("money", 0)) < money_cost:
            raise GameRuleError(f"You need {money_cost} Ryo to make that choice.")

        self.state["personal_actions_remaining"] -= personal_cost
        self.state["social_actions_remaining"] -= social_cost
        self.state["actions_remaining"] = self.state["personal_actions_remaining"] + self.state["social_actions_remaining"]
        wallet["money"] = int(wallet.get("money", 0)) - money_cost
        effects = choice.get("effects", {})
        self._apply_world_effects(effects)
        for npc_id, changes in effects.get("npc_relationships", {}).items():
            npc = next((item for item in self.state.get("npcs", []) if item.get("id") == npc_id), None)
            if npc is None or not isinstance(changes, dict):
                continue
            for key in ("affinity", "trust"):
                delta = changes.get(key)
                if isinstance(delta, (int, float)):
                    npc[key] = max(-100, min(100, int(npc.get(key, 0)) + int(delta)))
            npc["reaction"] = self._npc_reaction(npc)
            npc.setdefault("memories", []).append(f"You decided to {choice.get('label', 'respond')} when an opportunity arose.")
            npc["memories"] = npc["memories"][-20:]
        pending.remove(queued)
        self.state["world"].setdefault("opportunities_resolved", []).append({
            "id": opportunity_id,
            "choice_id": choice_id,
            "year": int(self.state.get("year", 1)),
        })
        self.state["world"]["opportunities_resolved"] = self.state["world"]["opportunities_resolved"][-40:]
        memory = effects.get("memory") if isinstance(effects, dict) else None
        if isinstance(memory, str) and memory:
            self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: {memory}")
        self._refresh_world_pack_unlocks()
        self._refresh_world_opportunities()
        self._save()
        return self.public_state()

    def _reset_world_action_budget(self) -> None:
        budget = get_action_budget(self.state.get("player", {}).get("age", 0))
        self.state["action_budget"] = budget
        self.state["personal_actions_remaining"] = budget["personal"]
        self.state["social_actions_remaining"] = budget["social"]
        # Retain a combined count for old tooling that only understands one pool.
        self.state["actions_remaining"] = budget["personal"] + budget["social"]

    def _world_actions(self) -> list[dict[str, Any]]:
        pack = self._active_world_pack()
        actions: list[dict[str, Any]] = []
        encounter_active = bool(self.state.get("world", {}).get("active_encounter"))
        for action in pack["actions"].get("actions", []):
            presentation = deepcopy(action)
            presentation.pop("effects", None)
            reason = self._world_requirement_reason(action.get("requires", {}))
            if reason is None and encounter_active:
                reason = "Resolve the current encounter first."
            remaining_key = f"{action.get('action_type')}_actions_remaining"
            if reason is None and self.state.get(remaining_key, 0) <= 0:
                reason = f"No {action.get('action_type')} actions remain this year."
            presentation["available"] = reason is None
            presentation["lock_reason"] = reason
            presentation["is_training"] = self._is_training_action(action)
            actions.append(presentation)
        known_techniques = self._naruto_profile().get("techniques", [])
        known_ids = {item.get("id") for item in known_techniques}
        for technique in pack.get("progression", {}).get("techniques", []):
            requirements = technique.get("learn_requirements")
            if not isinstance(requirements, dict) or technique.get("id") in known_ids:
                continue
            reason = self._world_requirement_reason(requirements)
            if reason is None and encounter_active:
                reason = "Resolve the current encounter first."
            if reason is None and int(self.state.get("personal_actions_remaining", 0)) <= 0:
                reason = "No personal actions remain this year."
            actions.append({
                "id": f"learn_technique_{technique['id']}",
                "label": f"Learn {technique.get('name', 'new technique')}",
                "description": technique.get("description", "Study a new pack-defined technique."),
                "category": technique.get("learn_category", "Ninjutsu"),
                "action_type": "personal",
                "requires": deepcopy(requirements),
                "available": reason is None,
                "lock_reason": reason,
                "tier": int(technique.get("tier", 1)),
                "is_training": False,
            })
        for technique in known_techniques:
            cost = self._technique_chakra_cost(technique)
            available = self.state.get("personal_actions_remaining", 0) > 0 and self._naruto_profile().get("chakra_current", 0) >= cost
            if encounter_active:
                available = False
            reason = None if available else (
                "Resolve the current encounter first." if encounter_active
                else "Not enough chakra." if self.state.get("personal_actions_remaining", 0) > 0
                else "No personal actions remain this year."
            )
            actions.append({
                "id": f"practice_technique_{technique.get('id')}",
                "label": f"Practice {technique.get('name', 'Technique')}",
                "description": f"Practice this technique. Chakra cost: {cost}. Mastery: {technique.get('mastery', 0)}.",
                "category": "Ninjutsu",
                "action_type": "personal",
                "requires": {"technique_count": 1},
                "available": available,
                "chakra_cost": cost,
                "lock_reason": reason,
                "is_training": technique.get("type", "active") != "passive",
            })
        sage_mode = next((mode for mode in self._naruto_profile().get("modes", {}).values() if mode.get("tree") == "sage"), None)
        if sage_mode:
            reason = self._world_requirement_reason({"location": "training_ground", "age": int(sage_mode.get("practice_min_age", 16))})
            if self.state.get("personal_actions_remaining", 0) <= 0:
                reason = "No personal actions remain this year."
            actions.append({
                "id": "sage_mode_practice", "label": "Gather Natural Energy", "category": "Sage Training",
                "description": f"Train your nature-energy balance. Sage Mode mastery: {int(sage_mode.get('mastery', 0))}.",
                "action_type": "personal", "available": reason is None, "lock_reason": reason,
                "is_training": True,
            })
        affinity = self._naruto_profile().get("nature_affinity", {})
        current_nature = self._naruto_profile().get("chakra_nature", {}).get("id")
        refinement_names = {"wind": "Wind", "fire": "Fire", "water": "Water", "earth": "Earth", "lightning": "Lightning", "sand": "Sand", "ice": "Ice", "yin": "Yin", "yang": "Yang"}
        for nature_id, nature_name in refinement_names.items():
            if nature_id == current_nature or int(affinity.get(nature_id, 0)) >= 60:
                continue
            special = nature_id in {"yin", "yang"}
            requirements = {
                "age": 14 if special else 12,
                "location": "training_ground",
                "nature_ceremony_complete": True,
                "attributes": {"chakra_control": 35 if special else 25},
                "skills": {"ninjutsu": 18 if special else 12},
            }
            reason = self._world_requirement_reason(requirements)
            if reason is None and encounter_active:
                reason = "Resolve the current encounter first."
            if reason is None and int(self.state.get("personal_actions_remaining", 0)) <= 0:
                reason = "No personal actions remain this year."
            actions.append({
                "id": f"nature_affinity_practice_{nature_id}",
                "label": f"Explore {nature_name} Chakra Affinity",
                "description": f"Study the foundations of {nature_name} chakra as a secondary affinity. This may contribute to an advanced release.",
                "category": "Nature Shaping",
                "action_type": "personal",
                "requires": requirements,
                "available": reason is None,
                "lock_reason": reason,
                "is_training": True,
            })
        founded_ids = {item.get("id") for item in self.state.get("world", {}).get("founded_entities", [])}
        for founding in pack.get("organizations", {}).get("foundings", []):
            if founding.get("id") in founded_ids:
                continue
            requirements = founding.get("requirements", {})
            reason = self._world_requirement_reason(requirements)
            if reason is None and encounter_active:
                reason = "Resolve the current encounter first."
            if reason is None and int(self.state.get("personal_actions_remaining", 0)) <= 0:
                reason = "No personal actions remain this year."
            actions.append({
                "id": f"founding_{founding.get('id')}",
                "label": founding.get("label", "Establish an organization"),
                "description": founding.get("description", "Create a lasting institution."),
                "category": "World Building",
                "action_type": "personal",
                "requires": deepcopy(requirements),
                "available": reason is None,
                "lock_reason": reason,
                "costs": deepcopy(founding.get("costs", {})),
                "is_training": False,
            })
        for action in pack.get("people", {}).get("interactions", []):
            presentation = deepcopy(action)
            presentation.pop("relationship_effects", None)
            presentation.pop("effects", None)
            presentation.pop("memory", None)
            presentation["action_type"] = "social"
            presentation["available"] = self.state.get("social_actions_remaining", 0) > 0
            presentation["lock_reason"] = None if presentation["available"] else "No social actions remain this year."
            actions.append(presentation)
        return actions

    @staticmethod
    def _is_training_action(action: dict[str, Any]) -> bool:
        if not isinstance(action, dict):
            return False
        effects = action.get("effects", {})
        if not isinstance(effects, dict) or effects.get("learn_technique"):
            return False
        if action.get("training") is True:
            return True
        if any(key in effects for key in ("practice_technique", "practice_sage_mode")):
            return True
        return str(action.get("category", "")).lower() in {
            "foundation", "crafting", "body", "academy", "chakra", "specialist control",
            "nature shaping", "clan path", "sage training",
        }

    def _recommended_world_actions(self) -> list[dict[str, Any]]:
        """Rank available training choices while avoiding obsolete beginner drills."""
        profile = self._naruto_profile()
        attrs = profile.get("attributes", {})
        skills = profile.get("skills", {})
        candidates = []
        action_data = {item.get("id"): item for item in self._active_world_pack().get("actions", {}).get("actions", [])}
        for action in self._world_actions():
            if not action.get("available") or not action.get("is_training"):
                continue
            action_id = str(action.get("id", ""))
            category = str(action.get("category", "")).lower()
            if action_id == "train_chakra_control" and max(int(attrs.get("chakra_control", 0)), int(skills.get("ninjutsu", 0))) >= 50:
                continue
            if action_id == "academy_study" and int(attrs.get("academy_knowledge", 0)) >= 60:
                continue
            if action_id == "train_body" and int(attrs.get("body_conditioning", 0)) >= 65:
                continue
            source = action_data.get(action_id, {})
            effects = source.get("effects", {}) if isinstance(source, dict) else {}
            score = 0.0
            targets = effects.get("attributes", {}) if isinstance(effects, dict) else {}
            for key, amount in targets.items():
                if isinstance(amount, (int, float)) and amount > 0:
                    score += max(0, 80 - int(attrs.get(key, 0))) / 20
            xp_targets = effects.get("skill_xp", {}) if isinstance(effects, dict) else {}
            for key, amount in xp_targets.items():
                if isinstance(amount, (int, float)) and amount > 0:
                    score += max(0, 75 - int(skills.get(key, 0))) / 16
            if "nature" in category or action_id.startswith("nature_affinity_"):
                score += 2
            if effects.get("skill_points"):
                score += 1.5
            if not source and action_id.startswith("practice_technique_"):
                score += 1 + max(0, 30 - int(next((t.get("level", 1) for t in profile.get("techniques", []) if action_id.endswith(str(t.get("id")))), 1))) / 30
            action_copy = deepcopy(action)
            action_copy["recommendation_reason"] = self._training_recommendation_reason(action_copy, attrs, skills)
            candidates.append((score, action_copy))
        candidates.sort(key=lambda row: (-row[0], row[1].get("label", "")))
        return [item for _, item in candidates[:3]]

    @staticmethod
    def _training_recommendation_reason(action: dict[str, Any], attrs: dict[str, Any], skills: dict[str, Any]) -> str:
        action_id = str(action.get("id", ""))
        if "nature_affinity" in action_id:
            return "Build a secondary affinity toward advanced nature releases."
        if "chakra" in action_id or "sage" in action_id:
            return f"Develop chakra control ({int(attrs.get('chakra_control', 0))}) for higher-tier techniques."
        if "academy" in action_id or "study" in action_id:
            return f"Improve academy knowledge ({int(attrs.get('academy_knowledge', 0))}) for rank and jutsu requirements."
        if "spar" in action_id or "taijutsu" in action_id or "body" in action_id:
            return f"Build combat fundamentals; Taijutsu is level {int(skills.get('taijutsu', 0))}."
        return "This activity advances a skill or attribute that is still developing."

    def _roll_training_effects(self, action: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Roll variable 1-4 training gains and a trait-modified critical success."""
        effects = deepcopy(action.get("effects", {}))
        if not self._is_training_action(action):
            return effects, {"is_training": False, "critical": False}
        for section in ("attributes", "skill_xp", "nature_affinity"):
            values = effects.get(section, {})
            if not isinstance(values, dict):
                continue
            for key, amount in list(values.items()):
                if isinstance(amount, (int, float)) and amount > 0:
                    values[key] = random.randint(1, 4)
        for key in ("practice_technique", "practice_sage_mode"):
            practice = effects.get(key)
            if isinstance(practice, dict) and isinstance(practice.get("mastery"), (int, float)):
                practice["mastery"] = random.randint(1, 4)
        traits = self._naruto_profile().get("traits", [])
        critical_bonus = sum(
            float(trait.get("modifiers", {}).get("training_crit_chance_percent", 0))
            for trait in traits
        )
        chance = max(0.02, min(0.60, 0.08 + critical_bonus / 100))
        critical = random.random() < chance
        if critical:
            for section in ("attributes", "skill_xp", "nature_affinity"):
                values = effects.get(section, {})
                if isinstance(values, dict):
                    for key, amount in values.items():
                        if isinstance(amount, (int, float)) and amount > 0:
                            values[key] = int(amount) * 2
            for key in ("practice_technique", "practice_sage_mode"):
                practice = effects.get(key)
                if isinstance(practice, dict) and isinstance(practice.get("mastery"), (int, float)):
                    practice["mastery"] = int(practice["mastery"]) * 2
        return effects, {"is_training": True, "critical": critical, "critical_chance": round(chance * 100)}

    def _complete_founding(self, founding: dict[str, Any]) -> None:
        entity = deepcopy(founding.get("entity", {}))
        if not entity.get("id"):
            return
        entity.update({
            "founded_by": self.state.get("player", {}).get("name", "A shinobi"),
            "founded_year": int(self.state.get("year", 1)),
            "region_id": self.state.get("world", {}).get("current_region"),
            "level": 1,
            "influence": 1,
            "dynamic": True,
        })
        world = self.state.setdefault("world", {})
        founded = world.setdefault("founded_entities", [])
        if any(item.get("id") == entity["id"] for item in founded):
            return
        founded.append(entity)
        world.setdefault("organizations", {})[entity["id"]] = {"influence": 1, "level": 1}
        world.setdefault("chronicle", []).append({
            "year": int(self.state.get("year", 1)),
            "text": f"{entity.get('name', 'A new organization')} was founded by {entity['founded_by']} in {entity.get('region_id', 'the shinobi world')}.",
            "kind": "founding",
        })
        world["chronicle"] = world["chronicle"][-80:]
        self._record_world_memory(f"You founded {entity.get('name', 'a new organization')}; its future now depends on those who join it.")

    def _technique_chakra_cost(self, technique: dict[str, Any]) -> int:
        base_cost = max(0, int(technique.get("chakra_cost", 0)))
        reduction = sum(int(item.get("modifiers", {}).get("chakra_cost_percent", 0)) for item in self._naruto_profile().get("traits", []))
        return max(0, int(round(base_cost * max(0, 100 + reduction) / 100)))

    def interact_with_world_npc(self, npc_id: str, interaction_id: str) -> dict[str, Any]:
        """Spend a social action on a persistent world-pack character."""
        self._require_state()
        pack = self._active_world_pack()
        if self.state.get("social_actions_remaining", 0) <= 0:
            raise GameRuleError("No social actions remain this year.")
        npc = next((person for person in self.state.get("npcs", []) if person.get("id") == npc_id), None)
        if npc is None:
            raise GameRuleError("That person is not part of this life.")
        interaction = next(
            (item for item in pack.get("people", {}).get("interactions", []) if item.get("id") == interaction_id),
            None,
        )
        if interaction is None:
            raise GameRuleError("That interaction is not available in this world pack.")
        required_role = interaction.get("requires_role")
        if required_role and npc.get("role") != required_role:
            raise GameRuleError(f"{interaction['label']} requires an {required_role.lower()}.")
        minimum_age = int(interaction.get("min_age", 0))
        if int(self.state.get("player", {}).get("age", 0)) < minimum_age:
            raise GameRuleError(f"{interaction['label']} is available at age {minimum_age}.")
        if interaction.get("range") != "anywhere" and not self._world_person_is_here(npc):
            raise GameRuleError(f"Go to {self._world_person_location(npc).replace('_', ' ')} to spend time with {npc.get('name', 'them')}.")

        costs = interaction.get("costs", {})
        if not isinstance(costs, dict):
            costs = {}
        wallet = self.state["player"].setdefault("stats", {})
        money_cost = max(0, int(costs.get("money", 0)))
        if int(wallet.get("money", 0)) < money_cost:
            raise GameRuleError(f"You need {money_cost} Ryo to do that.")
        wallet["money"] = int(wallet.get("money", 0)) - money_cost

        for key, delta in interaction.get("relationship_effects", {}).items():
            if key in {"affinity", "trust"} and isinstance(delta, (int, float)):
                npc[key] = max(-100, min(100, int(npc.get(key, 0)) + int(delta)))
        role_to_bond = {
            "Parent": "family",
            "Academy peer": "academy_peers",
            "Academy instructor": "mentors",
        }
        bond_key = role_to_bond.get(npc.get("role"))
        if bond_key:
            trust_delta = interaction.get("relationship_effects", {}).get("trust", 0)
            bonds = self._naruto_profile()["relationships"]
            bonds[bond_key] = max(0, min(100, int(bonds.get(bond_key, 0)) + int(trust_delta)))
        self._apply_naruto_effects(interaction.get("effects", {}))
        self.state["social_actions_remaining"] -= 1
        self.state["actions_remaining"] = self.state.get("personal_actions_remaining", 0) + self.state["social_actions_remaining"]
        npc["last_interaction"] = interaction_id
        npc["last_interaction_year"] = int(self.state.get("year", 1))
        npc["reaction"] = self._npc_reaction(npc)
        rendered_memory = interaction.get("memory", "You spent time with {name}.").format(name=npc.get("name", "someone"))
        npc_memories = npc.setdefault("memories", [])
        npc_memories.append(rendered_memory)
        npc["memories"] = npc_memories[-20:]
        self._progress_world_quests("interact_with_npc", npc_id)
        self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: {rendered_memory}")
        self._refresh_world_pack_unlocks()
        self._refresh_world_opportunities()
        self._save()
        return self.public_state()

    def travel_world_location(self, location_id: str) -> dict[str, Any]:
        """Move between declared world-pack places without spending an action."""
        self._require_state()
        pack = self._active_world_pack()
        places = self._world_places(pack)
        place = next((item for item in places if item.get("id") == location_id), None)
        if place is None:
            raise GameRuleError("That place is not available in the current world pack.")
        world = self.state.setdefault("world", {})
        current_region = world.get("current_region", "land_of_fire")
        if place.get("region_id", current_region) != current_region:
            raise GameRuleError("That place is in another country. Travel there on the world map first.")
        previous = self.state["player"].get("location")
        self.state["player"]["location"] = location_id
        if previous != location_id:
            self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: You went to {place.get('name', location_id)}.")
            self._progress_world_quests("visit_location", location_id)
            self._refresh_world_opportunities()
        self._save()
        return self.public_state()

    def travel_world_region(self, region_id: str) -> dict[str, Any]:
        """Travel along declared map routes, spending one personal action."""
        self._require_state()
        pack = self._active_world_pack()
        regions = pack.get("regions", {}).get("regions", [])
        destination = next((item for item in regions if item.get("id") == region_id), None)
        if destination is None:
            raise GameRuleError("That region is not on this world map.")
        world = self.state.setdefault("world", {})
        current_id = world.get("current_region")
        current = next((item for item in regions if item.get("id") == current_id), None)
        if current is None:
            raise GameRuleError("Your current map location is unavailable.")
        if region_id == current_id:
            return self.public_state()
        if region_id not in current.get("routes", []):
            raise GameRuleError("There is no direct route. Travel through a connected region first.")
        if world.get("active_encounter"):
            raise GameRuleError("Resolve the current expedition encounter before travelling again.")
        if int(self.state.get("personal_actions_remaining", 0)) <= 0:
            raise GameRuleError("You need a personal action available to travel between regions.")
        world["current_region"] = region_id
        for person in self.state.get("npcs", []):
            if person.get("role") == "Blacksmith":
                person["region_id"] = region_id
                person["local_location"] = "blacksmith"
        self.state["player"]["location"] = destination.get("location_id", region_id)
        self.state["personal_actions_remaining"] -= 1
        self.state["actions_remaining"] = self.state["personal_actions_remaining"] + self.state.get("social_actions_remaining", 0)
        self._progress_world_quests("visit_region", region_id)
        self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: You travelled to {destination.get('name', region_id)}.")
        encounters = pack.get("regions", {}).get("encounters", [])
        available = {str(item) for item in destination.get("encounters", [])}
        candidates = [item for item in encounters if item.get("id") in available]
        seen_by_region = world.setdefault("encounters_seen_this_year", {})
        seen_ids = set(seen_by_region.get(region_id, []))
        unseen = [item for item in candidates if item.get("id") not in seen_ids]
        if not unseen and candidates:
            seen_ids.clear()
            unseen = candidates
        candidates = unseen
        if candidates:
            encounter = deepcopy(random.choice(candidates))
            seen_ids.add(encounter["id"])
            seen_by_region[region_id] = sorted(seen_ids)
            world["active_encounter"] = {
                "id": encounter["id"],
                "type": "expedition",
                "title": encounter.get("title", "An encounter on the road"),
                "description": encounter.get("description", "Something has happened nearby."),
                "choices": encounter.get("choices", []),
                "region_id": region_id,
            }
            world["active_encounter"]["description"] = self._narrate_world_event(
                world["active_encounter"]["title"], world["active_encounter"]["description"], "expedition"
            )
        self._refresh_world_opportunities()
        self._save()
        return self.public_state()

    def resolve_world_encounter(self, choice_id: str) -> dict[str, Any]:
        """Resolve a current expedition encounter with pack-authored effects."""
        self._require_state()
        encounter = self.state.get("world", {}).get("active_encounter")
        if not encounter:
            raise GameRuleError("There is no expedition encounter to resolve.")
        choice = next((item for item in encounter.get("choices", []) if item.get("id") == choice_id), None)
        if choice is None:
            raise GameRuleError("That encounter choice is no longer available.")
        effects = choice.get("effects", {})
        self._apply_world_effects(effects)
        memory = effects.get("memory") if isinstance(effects, dict) else None
        if isinstance(memory, str) and memory:
            self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: {memory}")
        self.state["world"]["active_encounter"] = None
        outcome = str(memory or f"You chose to {choice.get('label', 'respond').lower()} during {encounter.get('title', 'the encounter')}.")
        self.state["world"]["last_narration"] = self._narrate_world_event(
            encounter.get("title", "World encounter"), outcome, encounter.get("type", "encounter")
        )
        self._refresh_world_opportunities()
        self._save()
        return self.public_state()

    def start_world_combat(self, opponent_id: str) -> dict[str, Any]:
        """Begin a pack-defined supervised match; the opening consumes one action."""
        self._require_state()
        pack = self._active_world_pack()
        world = self.state.setdefault("world", {})
        if world.get("combat") and world["combat"].get("status") == "active":
            raise GameRuleError("Finish the current match before starting another.")
        spec = next((item for item in pack.get("combat", {}).get("opponents", []) if item.get("id") == opponent_id), None)
        if spec is None:
            raise GameRuleError("That opponent is not available in this world pack.")
        if int(self.state.get("personal_actions_remaining", 0)) <= 0:
            raise GameRuleError("No personal actions remain this year.")
        if int(self.state.get("player", {}).get("age", 0)) < int(spec.get("min_age", 0)):
            raise GameRuleError(f"Sparring is available at age {spec.get('min_age')}.")
        if self.state.get("player", {}).get("location") != spec.get("location"):
            raise GameRuleError(f"Travel to {spec.get('location', 'the training ground').replace('_', ' ').title()} first.")
        npc = next((person for person in self.state.get("npcs", []) if person.get("id") == spec.get("npc_id")), None)
        if npc is None or not self._world_person_is_here(npc):
            raise GameRuleError("Your sparring partner is not here.")
        profile = self._naruto_profile()
        attributes = self._effective_attributes(profile)
        opponent_power = max(1, int(npc.get("combat_power", spec.get("base_power", 18))))
        opponent_nature = str(spec.get("chakra_nature", npc.get("chakra_nature", ""))).lower()
        nature_edge = self._nature_matchup(profile.get("chakra_nature", {}).get("id", ""), opponent_nature)
        win_probability = self._combat_win_probability(self._combat_power(profile), opponent_power, nature_edge)
        self.state["personal_actions_remaining"] -= 1
        self.state["actions_remaining"] = self.state["personal_actions_remaining"] + self.state.get("social_actions_remaining", 0)
        world["combat"] = {
            "id": f"{opponent_id}:{self.state.get('year', 1)}:{self.state.get('personal_actions_remaining', 0)}",
            "opponent_id": opponent_id,
            "npc_id": npc["id"],
            "opponent_name": npc.get("name", "Opponent"),
            "mode": spec.get("mode", "sparring"),
            "status": "active",
            "round": 0,
            "max_rounds": int(pack.get("combat", {}).get("rules", {}).get("max_rounds", 8)),
            "player_hp": 26 + int(attributes.get("vitality", 0)) // 2,
            "player_max_hp": 26 + int(attributes.get("vitality", 0)) // 2,
            "opponent_hp": int(spec.get("base_hp", 28)),
            "opponent_max_hp": int(spec.get("base_hp", 28)),
            "opponent_power": opponent_power,
            "opponent_nature": opponent_nature,
            "nature_advantage": nature_edge,
            "player_win_probability": win_probability,
            "log": [f"The supervised spar begins. {npc.get('name', 'Your opponent')} watches your stance."],
            "year": int(self.state.get("year", 1)),
        }
        self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: You began a supervised spar with {npc.get('name', 'a training partner')}.")
        self._save()
        return self.public_state()

    def world_combat_turn(self, move_id: str) -> dict[str, Any]:
        """Resolve a deterministic, bounded sparring exchange using stats and jutsu."""
        self._require_state()
        pack = self._active_world_pack()
        world = self.state.setdefault("world", {})
        combat = world.get("combat")
        if not combat or combat.get("status") != "active":
            raise GameRuleError("There is no active match.")
        profile = self._naruto_profile()
        npc = next((person for person in self.state.get("npcs", []) if person.get("id") == combat.get("npc_id")), {})
        move = str(move_id or "").strip()
        guard = move == "guard"
        retreat = move == "retreat"
        technique = None
        if move.startswith("technique:"):
            technique_id = move.split(":", 1)[1]
            technique = next((item for item in profile.get("techniques", []) if item.get("id") == technique_id), None)
            if technique is None:
                raise GameRuleError("You have not learned that technique.")
            if technique.get("type", "active") == "passive":
                raise GameRuleError("Passive techniques cannot be selected as combat attacks.")
            chakra_cost = self._technique_chakra_cost(technique)
            if int(profile.get("chakra_current", 0)) < chakra_cost:
                raise GameRuleError(f"You need {chakra_cost} chakra to use {technique.get('name', 'that technique')}.")
            profile["chakra_current"] = int(profile.get("chakra_current", 0)) - chakra_cost
        elif move not in {"strike", "guard", "retreat"}:
            raise GameRuleError("Choose strike, guard, retreat, or a learned technique.")

        if retreat:
            cost = max(0, int(pack.get("combat", {}).get("rules", {}).get("retreat_health_cost", 3)))
            combat["player_hp"] = max(1, int(combat["player_hp"]) - cost)
            combat["status"] = "retreated"
            combat.setdefault("log", []).append(f"You yielded the match and took {cost} sparring damage while withdrawing.")
            self.state["player"].setdefault("ui_stats", {})["health"] = max(0, int(self.state["player"]["ui_stats"].get("health", 0)) - cost)
            world["last_combat"] = deepcopy(combat)
            world["combat"] = None
            self._save()
            return self.public_state()

        import hashlib
        seed_text = f"{combat.get('id')}:{combat.get('round', 0)}:{move}:{profile.get('skills', {}).get('taijutsu', 0)}"
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)
        attributes = self._effective_attributes(profile)
        skills = self._effective_skills(profile)
        base_attack = 4 + int(attributes.get("strength", 0)) // 8 + int(attributes.get("agility", 0)) // 16 + int(skills.get("taijutsu", 0)) // 10
        technique_power = (
            int(technique.get("combat_power", 0))
            + max(0, int(technique.get("level", 1)) - 1) * int(technique.get("power_per_level", 0))
            + max(0, int(technique.get("tier", 1)) - 1) * int(technique.get("power_per_tier", 2))
            + int(technique.get("mastery", 0)) // 15
        ) if technique else 0
        hit_chance = max(0.12, min(0.94, 0.50 + (self._combat_power(profile) - int(combat.get("opponent_power", 18))) / max(35, (self._combat_power(profile) + int(combat.get("opponent_power", 18))) * 2) + float(combat.get("nature_advantage", 0)) * 0.08))
        hit = not guard and rng.random() < hit_chance
        critical = hit and rng.random() < max(0.04, min(0.24, int(attributes.get("agility", 0)) / 500))
        attack = 0 if guard or not hit else base_attack + technique_power
        defense = int(combat.get("opponent_power", 18)) * 0.08 + 1
        dealt = max(0, int((attack - defense) * rng.uniform(1.18, 1.82))) if attack else 0
        if critical:
            dealt = int(dealt * 1.5)
        combat["opponent_hp"] = max(0, int(combat["opponent_hp"]) - dealt)
        round_number = int(combat.get("round", 0)) + 1
        combat["round"] = round_number
        combat.setdefault("log", []).append(
            f"Round {round_number}: You {'guarded carefully' if guard else f'used {technique.get("name")}' if technique else 'struck'} and {'landed a critical hit for ' + str(dealt) if critical else 'hit for ' + str(dealt) if hit else 'missed'} damage."
        )
        taken = 0
        if int(combat["opponent_hp"]) > 0:
            opponent_hit_chance = max(0.10, min(0.90, 1 - hit_chance + 0.06))
            opponent_attack = max(1, 1 + int(combat.get("opponent_power", 18)) // 14 + rng.randint(0, 3)) if rng.random() < opponent_hit_chance else 0
            taken = max(0, int(opponent_attack * 0.38)) if guard else opponent_attack
            combat["player_hp"] = max(0, int(combat["player_hp"]) - taken)
            combat["log"].append(f"{combat.get('opponent_name', 'Your partner')} answered for {taken} damage.")
        combat["log"] = combat["log"][-12:]
        won = int(combat["opponent_hp"]) <= 0
        lost = int(combat["player_hp"]) <= 0
        timed_out = round_number >= int(combat.get("max_rounds", 8))
        if timed_out and not (won or lost):
            roll = round(rng.random() * 100, 1)
            adjusted_probability = float(combat.get("player_win_probability", 50)) + (
                (int(combat["opponent_hp"]) / max(1, int(combat["opponent_max_hp"]))
                 - int(combat["player_hp"]) / max(1, int(combat["player_max_hp"]))) * 25
            )
            won = roll <= max(5, min(95, adjusted_probability)) and int(combat["player_hp"]) > 0
            lost = not won
            combat["resolution_roll"] = roll
            combat["resolution_probability"] = round(max(5, min(95, adjusted_probability)), 1)
            combat["log"].append(f"The judges compare the final positions. Your weighted result is {combat['resolution_roll']} against {combat['resolution_probability']}.")
        if won or lost:
            combat["status"] = "won" if won else "lost"
            rules = pack.get("combat", {}).get("rules", {})
            self._apply_world_effects(rules.get("win_rewards" if won else "loss_rewards", {}))
            health_loss = max(1, int(combat["player_max_hp"]) - int(combat["player_hp"]))
            self.state["player"].setdefault("ui_stats", {})["health"] = max(0, int(self.state["player"]["ui_stats"].get("health", 0)) - max(1, health_loss // 3))
            if won:
                npc["trust"] = min(100, int(npc.get("trust", 0)) + 1)
                npc["affinity"] = min(100, int(npc.get("affinity", 0)) + 1)
                combat["log"].append("The match ends cleanly. You earned a little more trust through practice.")
            else:
                combat["log"].append("The instructor calls the match. You have something specific to train next time.")
            combat["log"] = combat["log"][-12:]
            world["last_combat"] = deepcopy(combat)
            world["combat"] = None
            self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: You {('won' if won else 'lost')} a supervised spar with {npc.get('name', 'a training partner')}.")
        self._save()
        return self.public_state()

    def _eligible_world_quest_templates(self, npc: dict[str, Any]) -> list[dict[str, Any]]:
        pack = self._active_world_pack()
        age = int(self.state.get("player", {}).get("age", 0))
        active_template_ids = {
            item.get("template_id") for item in self.state.get("world", {}).get("quests", [])
            if item.get("status") in {"offered", "accepted", "assigned"}
        }
        return [
            item for item in pack.get("quests", {}).get("templates", [])
            if npc.get("role") in item.get("giver_roles", [])
            and age >= int(item.get("min_age", 0))
            and item.get("id") not in active_template_ids
        ]

    def _offer_world_quest(self, npc: dict[str, Any], template_id: str) -> dict[str, Any] | None:
        template = next((item for item in self._eligible_world_quest_templates(npc) if item.get("id") == template_id), None)
        if template is None:
            return None
        quest = {
            "id": f"{template['id']}_{int(self.state.get('year', 1))}_{len(self.state['world'].setdefault('quests', [])) + 1}",
            "template_id": template["id"],
            "title": template.get("name", "Village assignment"),
            "type": template.get("type", "personal_quest"),
            "briefing": template.get("completion", "Complete the stated objective and report back.")[:400],
            "objective": deepcopy(template.get("objective", {})),
            "reward": deepcopy(template.get("reward", {})),
            "completion": template.get("completion", "The task is complete."),
            "offered_by": npc.get("id"),
            "offered_by_name": npc.get("name", "A villager"),
            "status": "offered",
            "progress": 0,
            "created_year": int(self.state.get("year", 1)),
        }
        self.state["world"].setdefault("quests", []).append(quest)
        return quest

    def talk_to_world_npc(self, npc_id: str, message: str) -> dict[str, Any]:
        """Have free-form dialogue with a present NPC; only pack quests affect rules."""
        self._require_state()
        npc = next((person for person in self.state.get("npcs", []) if person.get("id") == npc_id), None)
        if npc is None:
            raise GameRuleError("That person is not part of this life.")
        if not self._world_person_is_here(npc):
            raise GameRuleError(f"{npc.get('name', 'That person')} is not here. Travel to {self._world_person_location(npc).replace('_', ' ')} to talk.")
        clean_message = str(message or "").strip()
        if not clean_message:
            raise GameRuleError("Write a message before sending it.")
        if len(clean_message) > 1200:
            raise GameRuleError("Keep each message to 1,200 characters or fewer.")
        pack = self._active_world_pack()
        context = build_npc_context(self.state, npc, pack)
        model_reply = generate_npc_dialogue(npc.get("name", "Resident"), context, clean_message)
        eligible = self._eligible_world_quest_templates(npc)
        template_id = model_reply.get("quest_template_id") if model_reply else None
        eligible_ids = {item.get("id") for item in eligible}
        if template_id not in eligible_ids:
            lowered = clean_message.lower()
            if any(word in lowered for word in ("mission", "quest", "assignment", "work", "help")) and eligible:
                template_id = eligible[0].get("id")
            else:
                template_id = None
        lowered = clean_message.lower()
        job_id = model_reply.get("job_id") if model_reply else None
        job_intent = any(word in lowered for word in ("job", "work", "position", "employment", "career", "apprentice", "smith"))
        contact_job_ids = {
            item.get("id") for item in pack.get("careers", {}).get("jobs", [])
            if item.get("contact_id", "mission_clerk") == npc_id
        }
        if not contact_job_ids or not job_intent:
            job_id = None
        eligible_jobs = [
            item for item in self._world_career_state(pack).get("jobs", [])
            if item.get("available")
        ]
        eligible_job_ids = {item.get("id") for item in eligible_jobs} & contact_job_ids
        if job_id not in eligible_job_ids:
            model_requested_invalid_job = bool(job_id)
            job_id = None
            if not model_requested_invalid_job and job_intent:
                job_id = next((item.get("id") for item in eligible_jobs if item.get("id") in contact_job_ids), None)
        reply = model_reply.get("reply") if model_reply else None
        if not isinstance(reply, str) or not reply.strip():
            role = str(npc.get("role", "resident")).lower()
            if "instructor" in role or "clerk" in role:
                reply = "Tell me what you have been working on. Consistency matters more than trying to impress me in one day."
            elif "parent" in role or "guardian" in role:
                reply = "I am glad you came to talk. Tell me what has been on your mind lately."
            else:
                reply = "I hear you. What do you think you will do next?"
        history = npc.setdefault("chat_history", [])
        history.extend([
            {"speaker": "player", "text": clean_message[:1200], "year": int(self.state.get("year", 1))},
            {"speaker": "npc", "text": reply[:900], "year": int(self.state.get("year", 1))},
        ])
        npc["chat_history"] = history[-24:]
        memories = npc.setdefault("memories", [])
        memories.append(f"Age {self.state['player'].get('age', 0)}: You talked about: {clean_message[:100]}.")
        npc["memories"] = memories[-20:]
        if len(clean_message.split()) >= 4 and npc.get("chat_bond_year") != int(self.state.get("year", 1)):
            npc["affinity"] = min(100, int(npc.get("affinity", 0)) + 1)
            npc["chat_bond_year"] = int(self.state.get("year", 1))
            npc["reaction"] = self._npc_reaction(npc)
        quest = self._offer_world_quest(npc, template_id) if template_id else None
        job = None
        if job_id:
            jobs = [item for item in pack.get("careers", {}).get("jobs", []) if item.get("id") == job_id]
            if jobs:
                self.apply_for_world_job(job_id)
                job = jobs[0]
                reply += f" I can offer you the {job.get('name', 'position')}. Your shifts will be at {job.get('location', 'the workplace').replace('_', ' ').title()}."
                if history and history[-1].get("speaker") == "npc":
                    history[-1]["text"] = reply[-900:]
                npc["chat_history"] = history[-24:]
        self.state.setdefault("world", {})["last_chat"] = {
            "npc_id": npc_id, "npc_name": npc.get("name", "Resident"), "reply": reply[:900],
            "quest_id": quest.get("id") if quest else None,
            "job_id": job.get("id") if job else None,
        }
        self._save()
        return self.public_state()

    def accept_world_quest(self, quest_id: str) -> dict[str, Any]:
        self._require_state()
        quest = next((item for item in self.state.get("world", {}).get("quests", []) if item.get("id") == quest_id), None)
        if quest is None or quest.get("status") != "offered":
            raise GameRuleError("That quest is not awaiting your response.")
        quest["status"] = "accepted"
        self._save()
        return self.public_state()

    def assign_world_quest(self, quest_id: str, npc_id: str) -> dict[str, Any]:
        """Delegate an accepted mission to a trusted nearby character."""
        self._require_state()
        quest = next((item for item in self.state.get("world", {}).get("quests", []) if item.get("id") == quest_id), None)
        if quest is None or quest.get("status") != "accepted":
            raise GameRuleError("Only an accepted quest can be delegated.")
        if int(self.state.get("social_actions_remaining", 0)) <= 0:
            raise GameRuleError("No social actions remain this year.")
        npc = next((person for person in self.state.get("npcs", []) if person.get("id") == npc_id), None)
        if npc is None or not self._world_person_is_here(npc):
            raise GameRuleError("That person must be here before you can delegate the mission.")
        if int(npc.get("trust", 0)) < 15:
            raise GameRuleError("Build at least 15 trust before asking them to take a mission for you.")
        quest["status"] = "assigned"
        quest["assigned_to"] = npc_id
        quest["assigned_to_name"] = npc.get("name", "Teammate")
        self.state["social_actions_remaining"] -= 1
        self.state["actions_remaining"] = self.state.get("personal_actions_remaining", 0) + self.state["social_actions_remaining"]
        npc.setdefault("memories", []).append(f"You trusted them with the mission: {quest.get('title', 'an assignment')}.")
        npc["memories"] = npc["memories"][-20:]
        self._save()
        return self.public_state()

    def _progress_world_quests(self, event_type: str, target: str) -> None:
        for quest in self.state.get("world", {}).get("quests", []):
            if quest.get("status") != "accepted":
                continue
            objective = quest.get("objective", {})
            if objective.get("type") != event_type:
                continue
            expected = str(objective.get("target", ""))
            matches = target == expected
            if event_type == "interact_with_npc" and not matches:
                npc = next((item for item in self.state.get("npcs", []) if item.get("id") == target), {})
                matches = expected in {npc.get("id"), npc.get("role")}
            if not matches:
                continue
            quest["progress"] = min(int(objective.get("count", 1)), int(quest.get("progress", 0)) + 1)
            if quest["progress"] >= int(objective.get("count", 1)):
                self._complete_world_quest(quest)

    def _complete_world_quest(self, quest: dict[str, Any]) -> None:
        if quest.get("status") == "completed":
            return
        self._apply_world_effects(quest.get("reward", {}))
        quest["status"] = "completed"
        quest["completed_year"] = int(self.state.get("year", 1))
        text = quest.get("completion", "The assignment is complete.")
        self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: Quest complete: {quest.get('title', 'Assignment')}. {text}")
        giver = next((item for item in self.state.get("npcs", []) if item.get("id") == quest.get("offered_by")), None)
        if giver:
            giver["trust"] = min(100, int(giver.get("trust", 0)) + 2)
            giver.setdefault("memories", []).append(f"You completed the assignment they gave you: {quest.get('title', 'an assignment')}.")
            giver["memories"] = giver["memories"][-20:]

    def _resolve_assigned_quests(self) -> None:
        """Resolve delegated missions with a stable, relationship/skill-based roll."""
        import hashlib

        for quest in self.state.get("world", {}).get("quests", []):
            if quest.get("status") != "assigned":
                continue
            npc = next((item for item in self.state.get("npcs", []) if item.get("id") == quest.get("assigned_to")), {})
            skill_total = sum(int(value) for value in self._naruto_profile().get("skills", {}).values())
            chance = min(0.92, 0.30 + int(npc.get("trust", 0)) / 200 + skill_total / 1600)
            seed = f"{quest.get('id')}:{quest.get('assigned_to')}:{self.state.get('year', 1)}"
            roll = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
            if roll < chance:
                self._complete_world_quest(quest)
                if npc:
                    npc["trust"] = min(100, int(npc.get("trust", 0)) + 2)
            else:
                quest["status"] = "accepted"
                quest.pop("assigned_to", None)
                quest.pop("assigned_to_name", None)
                quest["last_attempt"] = "Your teammate could not complete the task this year; the mission remains open."
                if npc:
                    npc.setdefault("memories", []).append(f"The mission did not go as planned: {quest.get('title', 'assignment')}.")
                    npc["memories"] = npc["memories"][-20:]

    def purchase_world_item(self, item_id: str) -> dict[str, Any]:
        """Purchase a declared pack item with village currency."""
        self._require_state()
        pack = self._active_world_pack()
        shop = self._active_region_shop(pack)
        if self.state.get("player", {}).get("location") != shop.get("location"):
            raise GameRuleError(f"Travel to {shop.get('name', 'the local shop')} before buying supplies.")
        item = next((entry for entry in shop.get("items", []) if entry.get("id") == item_id), None)
        if item is None:
            raise GameRuleError("That item is not stocked in this world pack.")
        player = self.state["player"]
        wallet = player.setdefault("stats", {})
        price = self._market_price(item, shop, pack)
        if int(wallet.get("money", 0)) < price:
            raise GameRuleError(f"You need {price} Ryo to buy {item.get('name', 'that item')}.")
        wallet["money"] = int(wallet.get("money", 0)) - price
        profile = self._naruto_profile()
        inventory = profile.setdefault("inventory", [])
        instance_id = f"{item['id']}:{int(self.state.get('year', 1))}:{len(inventory) + 1}"
        instance = deepcopy(item)
        instance.update({"id": item["id"], "template_id": item["id"], "instance_id": instance_id, "quantity": 1})
        instance["tier"] = max(1, min(9, int(instance.get("tier", 1))))
        inventory.append(instance)
        self._record_world_memory(f"Age {player.get('age', 0)}: You bought {item['name']} for {price} Ryo.")
        self._save()
        return self.public_state()

    def _active_region_shop(self, pack: dict[str, Any]) -> dict[str, Any]:
        data = pack.get("shops", {})
        shops = data.get("shops") if isinstance(data, dict) else None
        if isinstance(shops, list) and shops:
            region_id = self.state.get("world", {}).get("current_region")
            return deepcopy(next((shop for shop in shops if shop.get("region_id") == region_id), shops[0]))
        return deepcopy(data)

    def equip_world_item(self, instance_id: str) -> dict[str, Any]:
        """Equip a purchased item into its declared slot."""
        self._require_state()
        profile = self._naruto_profile()
        item = next((entry for entry in profile.get("inventory", []) if entry.get("instance_id") == instance_id), None)
        if not item or str(item.get("category", "")).lower() != "equipment":
            raise GameRuleError("That item is not equippable gear.")
        profile.setdefault("equipped", {})[str(item.get("slot", "tool"))] = instance_id
        self._save()
        return self.public_state()

    def forge_world_item(self, instance_id: str) -> dict[str, Any]:
        """Attempt a seeded, skill-influenced upgrade at the local blacksmith."""
        self._require_state()
        profile = self._naruto_profile()
        if self.state.get("player", {}).get("location") != "blacksmith":
            raise GameRuleError("Go to the Village Forge to improve equipment.")
        if int(self.state.get("personal_actions_remaining", 0)) <= 0:
            raise GameRuleError("No personal actions remain this year.")
        item = next((entry for entry in profile.get("inventory", []) if entry.get("instance_id") == instance_id), None)
        if not item or str(item.get("category", "")).lower() != "equipment":
            raise GameRuleError("Choose a piece of equipment from your inventory.")
        tier = max(1, min(9, int(item.get("tier", 1))))
        if tier >= 9:
            raise GameRuleError("Tier 9 is the highest equipment grade.")
        ingot = next((entry for entry in profile.get("inventory", []) if entry.get("id") == "iron_ingot" and int(entry.get("quantity", 1)) > 0), None)
        if not ingot:
            raise GameRuleError("Forging requires one Iron Ingot from a regional market.")
        cost = int(item.get("forge_base_cost", 20)) * tier
        wallet = self.state["player"].setdefault("stats", {})
        if int(wallet.get("money", 0)) < cost:
            raise GameRuleError(f"You need {cost} Ryo for this forging attempt.")
        wallet["money"] -= cost
        ingot["quantity"] = int(ingot.get("quantity", 1)) - 1
        if ingot["quantity"] <= 0:
            profile["inventory"].remove(ingot)
        smithing = int(profile.get("skills", {}).get("smithing", 0))
        chance = max(0.25, min(0.95, 0.72 + smithing / 250 - (tier - 1) * 0.055))
        import hashlib
        seed_text = f"forge:{instance_id}:{self.state.get('year', 1)}:{profile.get('skill_xp', {}).get('smithing', 0)}"
        rng = random.Random(int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16))
        succeeded = rng.random() < chance
        if succeeded:
            item["tier"] = tier + 1
            item.setdefault("forge_history", []).append({"from": tier, "to": tier + 1, "year": int(self.state.get("year", 1))})
        profile["skill_xp"]["smithing"] = int(profile["skill_xp"].get("smithing", 0)) + 8
        profile["skills"]["smithing"] = min(100, int(profile["skill_xp"]["smithing"]) // 10)
        self.state["personal_actions_remaining"] -= 1
        self.state["actions_remaining"] = self.state["personal_actions_remaining"] + self.state.get("social_actions_remaining", 0)
        result = f"Tetsu raised {item.get('name', 'your gear')} to tier {item['tier']}." if succeeded else f"The forging attempt failed. {item.get('name', 'Your gear')} remains tier {tier}, but Tetsu learned from the work."
        self.state.setdefault("world", {})["last_forge"] = {"item_id": instance_id, "succeeded": succeeded, "chance": round(chance * 100, 1), "result": result}
        self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: {result}")
        self._save()
        return self.public_state()

    def start_world_legacy_family(self, npc_id: str, child_name: str) -> dict[str, Any]:
        """Record a child with an adult, trusted partner for a future continuation."""
        self._require_state()
        player = self.state.get("player", {})
        if int(player.get("age", 0)) < 18:
            raise GameRuleError("You must be an adult before starting a family.")
        if int(self.state.get("social_actions_remaining", 0)) <= 0:
            raise GameRuleError("No social actions remain this year.")
        npc = next((person for person in self.state.get("npcs", []) if person.get("id") == npc_id), None)
        if not npc or npc.get("role") in {"Parent", "Blacksmith"}:
            raise GameRuleError("Choose an eligible adult from your relationships.")
        if int(npc.get("age", 0)) < 18:
            raise GameRuleError("Your partner must also be an adult.")
        if not self._world_person_is_here(npc):
            raise GameRuleError(f"Meet {npc.get('name', 'them')} at {self._world_person_location(npc).replace('_', ' ')} first.")
        if int(npc.get("affinity", 0)) < 25 or int(npc.get("trust", 0)) < 25:
            raise GameRuleError("Starting a family requires at least 25 affinity and 25 trust with this person.")
        child_name = str(child_name or "").strip()[:32]
        if not child_name:
            raise GameRuleError("Choose a name for your child.")
        profile = self._naruto_profile()
        legacy = self.state.setdefault("world", {}).setdefault("legacy", {"generation": 1, "generations": [], "heirs": []})
        heirs = legacy.setdefault("heirs", [])
        if len(heirs) >= 10:
            raise GameRuleError("Your family record already has ten heirs; continue or archive a branch first.")
        heir = {
            "id": f"heir_{int(self.state.get('year', 1))}_{len(heirs) + 1}",
            "name": child_name,
            "age": 0,
            "status": "available",
            "parent_name": player.get("name", "Shinobi"),
            "partner_name": npc.get("name", "Partner"),
            "partner_id": npc_id,
            "clan": deepcopy(profile.get("clan", {"id": "civilian", "name": "Civilian-born"})),
            "village": deepcopy(profile.get("village", {"id": "leaf", "name": "Hidden Leaf"})),
            "chakra_nature": deepcopy(profile.get("chakra_nature", {"id": "wind", "name": "Wind"})),
            "created_year": int(self.state.get("year", 1)),
        }
        heirs.append(heir)
        npc.setdefault("memories", []).append(f"You and {player.get('name', 'your partner')} started a family; your child is {child_name}.")
        npc["memories"] = npc["memories"][-20:]
        self.state["social_actions_remaining"] -= 1
        self.state["actions_remaining"] = int(self.state.get("personal_actions_remaining", 0)) + self.state["social_actions_remaining"]
        self._record_world_memory(f"Age {player.get('age', 0)}: You welcomed {child_name} into the family with {npc.get('name', 'your partner')}.")
        self._save()
        return self.public_state()

    def _begin_next_legacy_life(self, name: str, village_id: str, clan_id: str, nature_id: str, continuation: str, heir_id: str | None = None) -> dict[str, Any]:
        """Start a new character save while carrying forward the shared world and its memories."""
        self._require_state()
        previous = deepcopy(self.state)
        old_player = previous.get("player", {})
        old_world = previous.get("world", {})
        old_profile = old_player.get("naruto", {})
        old_age = int(old_player.get("age", 0))
        old_year = int(previous.get("year", 1))
        generation = max(1, int(old_world.get("legacy", {}).get("generation", 1)))
        legacy = deepcopy(old_world.get("legacy", {"generation": generation, "generations": [], "heirs": []}))
        if continuation == "child":
            heir = next((item for item in legacy.get("heirs", []) if item.get("id") == heir_id and item.get("status") == "available"), None)
            if not heir:
                raise GameRuleError("That heir is not available to continue.")
            name = str(heir.get("name", name))
            village_id = str(heir.get("village", {}).get("id", village_id))
            clan_id = str(heir.get("clan", {}).get("id", clan_id))
            nature_id = str(heir.get("chakra_nature", {}).get("id", nature_id))
            heir["status"] = "continued"
            for saved_heir in self.state.get("world", {}).get("legacy", {}).get("heirs", []):
                if saved_heir.get("id") == heir_id:
                    saved_heir["status"] = "continued"
        if old_age < 18:
            raise GameRuleError("A new generation becomes available after adulthood.")
        self._save()
        result = self.new_game(
            name, "", world_pack_id=str(old_world.get("pack_id", "naruto")),
            world_options={"age": 0, "village": village_id, "clan": clan_id, "chakra_nature": nature_id},
        )
        new_npcs = self.state.get("npcs", [])
        world = deepcopy(old_world)
        world["legacy"] = legacy
        world["legacy"]["generations"] = list(world["legacy"].get("generations", []))[-40:]
        world["legacy"]["generations"].append({
            "generation": generation,
            "name": old_player.get("name", "Unknown shinobi"),
            "age": old_age,
            "clan": old_profile.get("clan", {}).get("name", "Unknown lineage"),
            "year": old_year,
            "continued_as": continuation,
        })
        world["legacy"]["generation"] = generation + 1
        world["rank"] = "Academy Student"
        world["influence"] = 0
        world["title"] = "Unproven"
        world["quests"] = []
        world["combat"] = None
        world["unlocks"] = {}
        world["active_encounter"] = None
        world["current_region"] = old_world.get("home_region", old_world.get("current_region"))
        world["home_region"] = old_world.get("home_region", world.get("current_region"))
        self.state["world"] = world
        self.state["year"] = old_year
        self.state["npcs"] = deepcopy(previous.get("npcs", []))
        for npc in new_npcs:
            if npc.get("role") == "Parent" and continuation == "reincarnation":
                npc = deepcopy(npc)
                npc["id"] = f"reincarnation_family_{generation}"
                npc["name"] = f"{name}'s Guardian"
                npc["region_id"] = world.get("home_region")
                npc["local_location"] = "home"
                self.state["npcs"].append(npc)
                break
        if continuation == "child":
            partner = next(
                (npc for npc in self.state["npcs"] if npc.get("id") == heir.get("partner_id")),
                None,
            )
            if partner:
                partner["role"] = "Parent"
                partner["age"] = max(int(partner.get("age", 0)), old_age)
                partner["region_id"] = world.get("home_region")
                partner["location"] = "home"
                partner["local_location"] = "home"
                partner.setdefault("memories", []).append(
                    f"They raised {name} with {old_player.get('name', 'their partner')} and remember the previous generation."
                )
                partner["memories"] = partner["memories"][-20:]
            self.state["npcs"].append({
                "id": f"legacy_parent_{generation}", "name": old_player.get("name", "Your parent"),
                "role": "Parent", "age": old_age, "location": "home", "local_location": "home",
                "region_id": world.get("home_region"), "affinity": 55, "trust": 60,
                "memories": [f"They remember raising {name} and the life that came before."], "interaction_counts": {},
            })
        self.state["player"]["location"] = "home"
        self.state["player"]["stats"]["money"] = max(0, int(old_player.get("stats", {}).get("money", 0)) // 10) if continuation == "child" else 0
        self.state["memories"] = [f"Age 0: A new life begins in generation {generation + 1}. The world remembers {old_player.get('name', 'a former shinobi')}."]
        self._naruto_profile()["legacy_memory"] = f"The previous generation was {old_player.get('name', 'unknown')}, a {old_profile.get('clan', {}).get('name', 'shinobi')} who lived to age {old_age}."
        world.setdefault("chronicle", []).append({"year": old_year, "text": f"Generation {generation + 1} began: {name} was born through {continuation}.", "kind": "legacy"})
        world["chronicle"] = world["chronicle"][-80:]
        self._refresh_world_pack_unlocks()
        self._save()
        return self.public_state()

    def continue_world_as_heir(self, heir_id: str) -> dict[str, Any]:
        self._require_state()
        legacy = self.state.get("world", {}).get("legacy", {})
        heir = next((item for item in legacy.get("heirs", []) if item.get("id") == heir_id and item.get("status") == "available"), None)
        if not heir:
            raise GameRuleError("That heir is not ready to continue this family line.")
        return self._begin_next_legacy_life(
            str(heir.get("name", "Shinobi Heir")), str(heir.get("village", {}).get("id", "leaf")),
            str(heir.get("clan", {}).get("id", "civilian")), str(heir.get("chakra_nature", {}).get("id", "wind")),
            "child", heir_id,
        )

    def reincarnate_world_life(self, name: str, village_id: str = "", clan_id: str = "", nature_id: str = "") -> dict[str, Any]:
        """Begin a fresh family line in the persistent world, optionally choosing a new origin."""
        self._require_state()
        if int(self.state.get("player", {}).get("age", 0)) < 18:
            raise GameRuleError("Reincarnation is available after adulthood.")
        pack = self._active_world_pack()
        creation = pack.get("character_creation", {})
        old_profile = self._naruto_profile()
        clans = creation.get("clans", [])
        eligible_clans = [item for item in clans if item.get("id") != old_profile.get("clan", {}).get("id")] or clans
        clan_id = clan_id or random.choice(eligible_clans).get("id", "civilian")
        village_id = village_id or random.choice(creation.get("villages", [])).get("id", "leaf")
        nature_id = nature_id or random.choice(creation.get("chakra_natures", [])).get("id", "wind")
        return self._begin_next_legacy_life(str(name or "Reborn Shinobi").strip()[:32], village_id, clan_id, nature_id, "reincarnation")

    def apply_for_world_job(self, job_id: str) -> dict[str, Any]:
        """Accept a pack-defined job offer when age, rank, and location qualify."""
        self._require_state()
        pack = self._active_world_pack()
        job = next((item for item in pack.get("careers", {}).get("jobs", []) if item.get("id") == job_id), None)
        if job is None:
            raise GameRuleError("That job is not available in this village.")
        player = self.state["player"]
        if int(player.get("age", 0)) < int(job.get("min_age", 0)):
            raise GameRuleError(f"You must be at least {job['min_age']} to apply.")
        requirement_reason = self._world_requirement_reason(job.get("requirements", {}))
        if requirement_reason:
            raise GameRuleError(requirement_reason)
        application_location = job.get("application_location", job.get("location"))
        if player.get("location") != application_location:
            raise GameRuleError(f"Speak with the village contact at {application_location.replace('_', ' ').title()} to apply.")
        if self._naruto_profile().get("career", {}).get("job_id"):
            raise GameRuleError("You already have a position. Resign or finish that role before taking another.")
        current_rank = self.state.get("world", {}).get("rank", "Academy Student")
        rank_order = {"Academy Student": 0, "Genin": 1, "Chunin": 2, "Jonin": 3}
        if rank_order.get(current_rank, 0) < rank_order.get(job.get("min_rank"), 0):
            raise GameRuleError(f"This position requires {job.get('min_rank')} rank.")
        career = self._naruto_profile().setdefault("career", {})
        career.update({"job_id": job_id, "experience": 0, "title": job["name"]})
        self._record_world_memory(f"Age {player.get('age', 0)}: You started work as a {job['name']}.")
        self._save()
        return self.public_state()

    def work_world_job(self) -> dict[str, Any]:
        """Spend a personal action working and evaluate deterministic promotions."""
        self._require_state()
        pack = self._active_world_pack()
        profile = self._naruto_profile()
        career = profile.get("career", {})
        job = next((item for item in pack.get("careers", {}).get("jobs", []) if item.get("id") == career.get("job_id")), None)
        if job is None:
            raise GameRuleError("Apply for a village job before working.")
        if int(self.state.get("personal_actions_remaining", 0)) <= 0:
            raise GameRuleError("No personal actions remain this year.")
        if self.state["player"].get("location") != job.get("location"):
            raise GameRuleError(f"Travel to {job['location'].replace('_', ' ').title()} for your shift.")
        experience = int(career.get("experience", 0)) + int(job.get("work_xp", 1))
        previous_title = career.get("title", job["name"])
        title, base_pay = job["name"], int(job.get("pay", 0))
        for promotion in job.get("promotions", []):
            if experience >= int(promotion.get("work_xp", 0)):
                title, base_pay = promotion.get("title", title), int(promotion.get("pay", base_pay))
        pay = self._regional_economy_value(base_pay, job.get("location"), pack)
        income_bonus = sum(float(item.get("modifiers", {}).get("income_percent", 0)) for item in profile.get("traits", []))
        pay += max(0, int(pay * income_bonus / 100))
        career.update({"experience": experience, "title": title})
        self._apply_naruto_effects({"skill_xp": job.get("skill_xp", {})})
        self.state["player"].setdefault("stats", {})["money"] = int(self.state["player"].get("stats", {}).get("money", 0)) + pay
        self.state["personal_actions_remaining"] -= 1
        self.state["actions_remaining"] = self.state["personal_actions_remaining"] + self.state.get("social_actions_remaining", 0)
        changed_title = title != previous_title
        note = f"You completed a shift as {title} and earned {pay} Ryo."
        self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: {note}")
        if changed_title:
            self._record_world_memory(f"Age {self.state['player'].get('age', 0)}: Your work earned a promotion to {title}.")
        self._save()
        return self.public_state()

    @staticmethod
    def _npc_reaction(npc: dict[str, Any]) -> str:
        """Describe how the NPC currently responds to the player's relationship."""
        affinity = int(npc.get("affinity", 0))
        trust = int(npc.get("trust", 0))
        if trust >= 55 and affinity >= 45:
            return "They trust you deeply and treat you as one of their closest people."
        if trust >= 25:
            return "They trust you and are willing to rely on you."
        if affinity >= 25:
            return "They enjoy your company and look forward to seeing you."
        if affinity < 0:
            return "They remain guarded around you."
        return "They are still getting to know you."

    def _training_unlocks(self) -> list[dict[str, Any]]:
        pack = self._active_world_pack()
        world_unlocks = self.state.get("world", {}).get("unlocks", {})
        entries: list[dict[str, Any]] = []
        for unlock in pack["progression"].get("unlocks", []):
            item = deepcopy(unlock)
            item["unlocked"] = bool(world_unlocks.get(unlock.get("id")))
            item["lock_reason"] = None if item["unlocked"] else self._world_requirement_reason(unlock.get("requirements", {}))
            entries.append(item)
        return entries

    def perform_world_action(self, action_id: str) -> dict[str, Any]:
        """Spend one annual action on a declared world-pack action."""
        self._require_state()
        pack = self._active_world_pack()
        active_combat = self.state.get("world", {}).get("combat")
        if active_combat and active_combat.get("status") == "active":
            raise GameRuleError("Finish the active spar before making another choice.")
        if self.state.get("world", {}).get("active_encounter"):
            raise GameRuleError("Resolve the current encounter before choosing another action.")
        action = get_pack_action(pack["manifest"]["id"], action_id)
        founding_definition = None
        if action is None and action_id.startswith("practice_technique_"):
            technique_id = action_id.removeprefix("practice_technique_")
            known_ids = {item.get("id") for item in self._naruto_profile().get("techniques", [])}
            if technique_id not in known_ids:
                raise GameRuleError("You have not learned that technique.")
            action = {
                "id": action_id,
                "action_type": "personal",
                "requires": {"technique_count": 1},
                "effects": {
                    "practice_technique": {
                        "technique_id": technique_id,
                        "mastery": 4,
                        "chakra_cost": self._technique_chakra_cost(next(item for item in self._naruto_profile()["techniques"] if item.get("id") == technique_id)),
                    },
                    "skill_points": 1,
                    "memory": "You practiced a known technique and improved its control.",
                },
                "training": True,
            }
        if action is None and action_id.startswith("learn_technique_"):
            technique_id = action_id.removeprefix("learn_technique_")
            technique = next((item for item in pack.get("progression", {}).get("techniques", []) if item.get("id") == technique_id), None)
            if technique and isinstance(technique.get("learn_requirements"), dict):
                action = {
                    "id": action_id,
                    "label": f"Learn {technique.get('name', 'technique')}",
                    "category": technique.get("learn_category", "Ninjutsu"),
                    "action_type": "personal",
                    "requires": deepcopy(technique["learn_requirements"]),
                    "effects": {"learn_technique": technique_id, "memory": f"You learned {technique.get('name', 'a new technique')} from deliberate training."},
                }
        if action is None and action_id.startswith("nature_affinity_practice_"):
            nature_id = action_id.removeprefix("nature_affinity_practice_")
            if nature_id in {"wind", "fire", "water", "earth", "lightning", "sand", "ice", "yin", "yang"}:
                special = nature_id in {"yin", "yang"}
                action = {
                    "id": action_id,
                    "label": f"Explore {nature_id.title()} Chakra Affinity",
                    "category": "Nature Shaping",
                    "action_type": "personal",
                    "requires": {
                        "age": 14 if special else 12,
                        "location": "training_ground",
                        "nature_ceremony_complete": True,
                        "attributes": {"chakra_control": 35 if special else 25},
                        "skills": {"ninjutsu": 18 if special else 12},
                    },
                    "effects": {"nature_affinity": {nature_id: 4}, "attributes": {"chakra_control": 1}, "skill_xp": {"ninjutsu": 2}, "memory": f"You studied the principles of {nature_id} chakra as a secondary affinity."},
                    "training": True,
                }
        if action is None and action_id.startswith("founding_"):
            founding_id = action_id.removeprefix("founding_")
            founding_definition = next((item for item in pack.get("organizations", {}).get("foundings", []) if item.get("id") == founding_id), None)
            if founding_definition:
                action = {
                    "id": action_id,
                    "label": founding_definition.get("label", "Establish an organization"),
                    "category": "World Building",
                    "action_type": "personal",
                    "requires": deepcopy(founding_definition.get("requirements", {})),
                    "costs": deepcopy(founding_definition.get("costs", {})),
                    "effects": {},
                }
        if action is None and action_id == "sage_mode_practice":
            sage_mode = next((mode for mode in self._naruto_profile().get("modes", {}).values() if mode.get("tree") == "sage"), None)
            if not sage_mode:
                raise GameRuleError("Unlock Sage Mode before practicing natural energy.")
            action = {
                "id": action_id, "action_type": "personal", "requires": {"age": int(sage_mode.get("practice_min_age", 16)), "location": "training_ground"},
                "costs": {"chakra": max(0, int(sage_mode.get("practice_chakra_cost", 3)))},
                "effects": {
                    "practice_sage_mode": {"mode_id": sage_mode.get("id"), "mastery": 25},
                    "attributes": {"willpower": 1, "chakra_control": 1},
                    "skill_xp": {"ninjutsu": 2}, "skill_points": 1,
                    "memory": "You balanced natural energy against your own chakra and deepened your Sage Mode mastery.",
                },
            }
        if action is None:
            raise GameRuleError("That action is not part of the current world pack.")
        reason = self._world_requirement_reason(action.get("requires", {}))
        if reason:
            raise GameRuleError(reason)
        action_type = action["action_type"]
        remaining_key = f"{action_type}_actions_remaining"
        if self.state.get(remaining_key, 0) <= 0:
            raise GameRuleError(f"No {action_type} actions remain this year.")

        costs = action.get("costs", {})
        chakra_cost = int(costs.get("chakra", 0)) if isinstance(costs, dict) else 0
        money_cost = max(0, int(costs.get("money", 0))) if isinstance(costs, dict) else 0
        practice = action.get("effects", {}).get("practice_technique", {})
        if isinstance(practice, dict):
            chakra_cost = max(chakra_cost, int(practice.get("chakra_cost", 0)))
        profile = self._naruto_profile()
        if int(profile.get("chakra_current", 0)) < chakra_cost:
            raise GameRuleError(f"You need {chakra_cost} chakra for that technique.")
        wallet = self.state["player"].setdefault("stats", {})
        if int(wallet.get("money", 0)) < money_cost:
            raise GameRuleError(f"You need {money_cost} Ryo for that action.")
        before_attributes = deepcopy(profile.get("attributes", {}))
        before_skill_xp = deepcopy(profile.get("skill_xp", {}))
        before_affinity = deepcopy(profile.get("nature_affinity", {}))
        before_technique_xp = {
            str(item.get("id")): int(item.get("xp", 0))
            for item in profile.get("techniques", [])
            if item.get("id")
        }
        profile["chakra_current"] = int(profile.get("chakra_current", 0)) - chakra_cost
        wallet["money"] = int(wallet.get("money", 0)) - money_cost
        effects, training_roll = self._roll_training_effects(action)
        self._apply_world_effects(effects)
        if founding_definition:
            self._complete_founding(founding_definition)
        self.state[remaining_key] -= 1
        self.state["actions_remaining"] = (
            self.state.get("personal_actions_remaining", 0)
            + self.state.get("social_actions_remaining", 0)
        )
        action_counts = self.state.setdefault("world", {}).setdefault("action_counts", {})
        action_counts[action_id] = int(action_counts.get(action_id, 0)) + 1
        if action_id == "adventure_expedition":
            self._begin_local_adventure()
        new_unlocks = self._refresh_world_pack_unlocks()
        self._progress_world_quests("perform_action", action_id)
        memory = effects.get("memory")
        if isinstance(memory, str) and memory:
            self._record_world_memory(f"Age {self.state['player']['age']}: {memory}")
        for unlock_id in new_unlocks:
            self._record_world_memory(f"Age {self.state['player']['age']}: Unlocked {unlock_id.replace('_', ' ').title()}.")
        if training_roll.get("is_training"):
            current_profile = self._naruto_profile()
            attribute_gains = {
                key: int(value) - int(before_attributes.get(key, 0))
                for key, value in current_profile.get("attributes", {}).items()
                if int(value) > int(before_attributes.get(key, 0))
            }
            xp_gains = {
                key: int(value) - int(before_skill_xp.get(key, 0))
                for key, value in current_profile.get("skill_xp", {}).items()
                if int(value) > int(before_skill_xp.get(key, 0))
            }
            affinity_gains = {
                key: int(value) - int(before_affinity.get(key, 0))
                for key, value in current_profile.get("nature_affinity", {}).items()
                if int(value) > int(before_affinity.get(key, 0))
            }
            technique_mastery_gains = {
                str(item.get("id")): int(item.get("xp", 0)) - before_technique_xp.get(str(item.get("id")), 0)
                for item in current_profile.get("techniques", [])
                if item.get("id") and int(item.get("xp", 0)) > before_technique_xp.get(str(item.get("id")), 0)
            }
            training_roll.update({
                "label": action.get("label", action_id),
                "attribute_gains": attribute_gains,
                "skill_xp_gains": xp_gains,
                "nature_affinity_gains": affinity_gains,
                "technique_mastery_gains": technique_mastery_gains,
                "mastery_gain": sum(technique_mastery_gains.values()),
                "technique": effects.get("practice_technique", {}).get("technique_id") if isinstance(effects.get("practice_technique"), dict) else None,
                "year": int(self.state.get("year", 1)),
            })
            self.state.setdefault("world", {})["last_action_result"] = training_roll
        self._refresh_world_opportunities()
        self._log("STATE", f"World action: {action_id} ({action_type})")
        self._save()
        return self.public_state()

    def _begin_local_adventure(self) -> dict[str, Any] | None:
        """Start a pack-authored encounter in the current region after an expedition action."""
        pack = self._active_world_pack()
        world = self.state.setdefault("world", {})
        if world.get("active_encounter"):
            return world["active_encounter"]
        region_id = world.get("current_region")
        region = next(
            (item for item in pack.get("regions", {}).get("regions", []) if item.get("id") == region_id),
            None,
        )
        if not region:
            return None
        encounter_ids = set(region.get("encounters", []))
        candidates = [
            item for item in pack.get("regions", {}).get("encounters", [])
            if item.get("id") in encounter_ids
        ]
        seen_by_region = world.setdefault("encounters_seen_this_year", {})
        seen_ids = set(seen_by_region.get(region_id, []))
        unseen = [item for item in candidates if item.get("id") not in seen_ids]
        if not unseen and candidates:
            seen_ids.clear()
            unseen = candidates
        if not unseen:
            return None
        encounter = deepcopy(random.choice(unseen))
        seen_ids.add(encounter["id"])
        seen_by_region[region_id] = sorted(seen_ids)
        active = {
            "id": encounter["id"],
            "type": "adventure",
            "title": encounter.get("title", "A trail-side encounter"),
            "description": encounter.get("description", "Something has happened nearby."),
            "choices": encounter.get("choices", []),
            "region_id": region_id,
        }
        active["description"] = self._narrate_world_event(active["title"], active["description"], "adventure")
        world["active_encounter"] = active
        return active

    def advance_world_year(self) -> dict[str, Any]:
        """End a world-pack year early or after all actions have been used."""
        self._require_state()
        self._active_world_pack()
        active_combat = self.state.get("world", {}).get("combat")
        if active_combat and active_combat.get("status") == "active":
            raise GameRuleError("Finish or retreat from the active spar before advancing the year.")
        if self.state.get("world", {}).get("active_encounter"):
            raise GameRuleError("Resolve the active encounter before advancing the year.")
        player = self.state["player"]
        player["age"] = max(0, int(player.get("age", 0)) + 1)
        player["life_stage"] = self._life_stage(player["age"])
        self._naruto_profile()["chakra_current"] = int(self._naruto_profile()["attributes"].get("chakra_capacity", 0))
        for npc in self.state.get("npcs", []):
            npc["age"] = max(0, int(npc.get("age", 0)) + 1)
        self.state["year"] = max(1, int(self.state.get("year", 1)) + 1)
        self._reset_world_action_budget()
        self.state.setdefault("world", {})["encounters_seen_this_year"] = {}
        self._resolve_assigned_quests()
        new_unlocks = self._refresh_world_pack_unlocks()
        self._record_world_memory(f"Age {player['age']}: A new year of shinobi life begins.")
        if int(player["age"]) == 5:
            self._conduct_chakra_nature_ceremony()
            new_unlocks.extend(self._refresh_world_pack_unlocks())
        else:
            self._maybe_trigger_world_disaster()
        for unlock_id in new_unlocks:
            self._record_world_memory(f"Age {player['age']}: Unlocked {unlock_id.replace('_', ' ').title()}.")
        self._refresh_world_opportunities()
        self._log("STATE", f"Advanced world-pack year to age {player['age']}")
        self._save()
        return self.public_state()

    def save_game(self) -> dict[str, Any]:
        """Persist the active save without advancing time or changing state."""
        self._require_state()
        self._save()
        return self.public_state()

    def load_game(self, game_folder: Path | None = None) -> dict[str, Any]:
        """Load a saved game.

        Args:
            game_folder: Optional path to a specific game folder. If not provided,
                attempts to load from the default fallback save file or find the
                latest game by player name.
        """
        # If a game folder is provided, use its save file
        if game_folder is not None:
            self._set_game_folder(game_folder)
        elif self._game_folder is not None:
            self.save_file = game_config.get_save_file_for_game(self._game_folder)

        if not self.save_file.exists():
            self._log("ERROR", "Load failed: no saved game found")
            raise GameRuleError("There is no saved game yet.")
        manifest = json.loads(self.save_file.read_text(encoding="utf-8"))
        if isinstance(manifest, dict) and manifest.get("format") == "riverton-save-v2":
            self.state = self._load_split_state(manifest)
        else:
            self.state = manifest
        self.state = normalize_state(self.state)
        self._ensure_progression_defaults()
        # Restore game folder from state if present
        if self._game_folder is None and self.state.get("game_folder"):
            found = game_config.get_game_folder(self.state["player"].get("name", ""), self.state["game_folder"])
            if found:
                self._set_game_folder(found)
        self._log("STATE", f"Loaded game: {self.state.get('player', {}).get('name', 'Unknown')} (Year {self.state.get('year', 1)})")
        return self.public_state()

    def travel(self, location: str) -> dict[str, Any]:
        self._require_state()
        if location not in LOCATIONS:
            self._log("ERROR", f"Travel failed: location '{location}' does not exist")
            raise GameRuleError("That location does not exist.")
        old_loc = self.state["player"]["location"]
        self.state["player"]["location"] = location
        self._memory(f"You visited {LOCATIONS[location]}.")
        self._log("STATE", f"Travel: {LOCATIONS.get(old_loc, old_loc)} -> {LOCATIONS.get(location, location)}")
        self._save()
        return self.public_state()

    def resolve_encounter(self, choice_id: str) -> dict[str, Any]:
        self._require_state()
        encounter = self._current_encounter()
        if not encounter:
            raise GameRuleError("There is no encounter to resolve right now.")
        choice = next((item for item in encounter.get("choices", []) if item.get("id") == choice_id), None)
        if not choice:
            raise GameRuleError("That choice is no longer available.")
        # Use framework system for events with a framework key
        if encounter.get("framework"):
            try:
                resolve_framework(self, encounter, choice_id)
            except FrameworkError as error:
                self._log("ERROR", f"Framework error: {error}")
                raise GameRuleError(str(error))
        elif encounter.get("type") == "education":
            self._resolve_education_encounter(choice_id, encounter)
        elif encounter.get("type") == "school_day":
            self._resolve_school_day(choice_id, encounter)
        elif encounter.get("id") == "school_graduation":
            self._resolve_school_graduation(choice_id, encounter)
        self.state.setdefault("memories", []).append(f"Encounter: {encounter.get('title', 'Unknown')}")
        self.state["encounters"] = []
        self._save()
        return self.public_state()

    def interact(self, npc_id: str, action: str) -> dict[str, Any]:
        self._require_state()
        npc = self._npc(npc_id)
        if npc["location"] != self.state["player"]["location"]:
            self._log("WARN", f"Interact failed: {npc['name']} is not at {self.state['player']['location']}")
            raise GameRuleError("That person is not here.")
        if self.state["completed"]:
            raise GameRuleError("This year is already complete.")
        if self.state["active_random_event"]:
            raise GameRuleError("Resolve the current event first.")
        if self.state["actions_remaining"] <= 0:
            raise GameRuleError("Use the main decision to continue to the next season.")
        actions = {
            "talk": ({"affinity": {npc_id: 1}}, "You had a good conversation with"),
            "help": ({"trust": {npc_id: 1}, "energy": -1}, "You made time to help"),
            "work": ({"money": 1, "energy": -1, "trust": {npc_id: 1}}, "You worked alongside"),
        }
        if action not in actions:
            raise GameRuleError("That interaction is not available.")
        effects, sentence = actions[action]
        self._apply_effects(effects)
        self.state["actions_remaining"] -= 1
        self._advance_age(0)
        self._memory(f"{sentence} {npc['name']}.")
        self._log("INFO", f"Interact: {action} with {npc['name']} (actions left: {self.state['actions_remaining']})")
        # Check for NPC arc milestones after interaction (before random events, so milestones take priority)
        self._check_npc_milestones()
        # Process any pending milestone events first
        if self.state.get("milestone_events_pending"):
            self.state["active_random_event"] = self.state["milestone_events_pending"].pop(0)
            self.state["random_seen_this_season"] = True
            self._log("EVENT", f"Milestone event triggered: {self.state['active_random_event'].get('title', 'Unknown')}")
        elif not self.state["random_seen_this_season"] and random.random() < 0.7:
            event = self._choose_random_event()
            if event:
                self.state["active_random_event"] = event
                self.state["random_seen_this_season"] = True
                self._log("EVENT", f"Random event triggered: {event.get('title', 'Unknown')}")
        self._save()
        return self.public_state()

    def choose_main(self, choice_id: str) -> dict[str, Any]:
        self._require_state()
        event = self._current_event()
        if not event or self.state["active_random_event"]:
            raise GameRuleError("Resolve the current event first.")
        if self.state["actions_remaining"] > 0:
            raise GameRuleError("Use your remaining season actions first.")
        choice = next((item for item in event["choices"] if item["id"] == choice_id), None)
        if not choice:
            raise GameRuleError("That choice is no longer available.")
        previous_state = {"player": deepcopy(self.state["player"]), "npcs": deepcopy(self.state["npcs"])}
        self._apply_effects(choice["effects"])
        self._memory(f"{SEASONS[self.state['season_index']]}: {choice['label']}.")
        season_name = SEASONS[self.state['season_index']]
        self._log("EVENT", f"Main choice: {season_name} - {choice['label']}")

        # Generate season narration using LLM
        try:
            from llm_service import generate_season_narration
            curr_player = self.state["player"]
            curr_npcs = self.state["npcs"]
            prev_stats = previous_state["player"].get("stats", {})
            curr_stats = curr_player.get("stats", {})
            stats_changes = []
            for stat in ("energy", "money", "skill", "reputation"):
                before = prev_stats.get(stat, 0)
                after = curr_stats.get(stat, 0)
                if after != before:
                    stats_changes.append(f"{stat} {before}->{after}")
            npc_changes = []
            prev_npcs_map = {n.get("id"): n for n in previous_state["npcs"]}
            for npc in curr_npcs:
                prev = prev_npcs_map.get(npc["id"], {})
                if npc.get("trust", 0) != prev.get("trust", 0) or npc.get("affinity", 0) != prev.get("affinity", 0):
                    npc_changes.append(f"{npc.get('name', npc['id'])} trust/affinity changed")
            narrated_summary = generate_season_narration(
                season=season_name,
                player_name=curr_player.get("name", "Player"),
                focus=choice["label"],
                stats_changes=stats_changes,
                npc_changes=npc_changes,
            )
            self.state["season_summary"] = narrated_summary
        except Exception:
            self.state["season_summary"] = build_season_summary(previous_state, {"player": deepcopy(self.state["player"]), "npcs": deepcopy(self.state["npcs"])}, choice["label"])

        self.state["season_index"] += 1
        self.state["actions_remaining"] = 3
        self.state["random_seen_this_season"] = False
        self._advance_age(1)
        if self.state["season_index"] >= len(MAIN_EVENTS):
            self.state["completed"] = True
            self._log("STATE", "Year completed!")
        self._save()
        return self.public_state()

    def choose_random(self, choice_id: str) -> dict[str, Any]:
        self._require_state()
        event = self.state.get("active_random_event")
        if not event:
            raise GameRuleError("There is no random event to resolve.")
        choice = next((item for item in event["choices"] if item["id"] == choice_id), None)
        if not choice:
            raise GameRuleError("That choice is no longer available.")
        self._apply_effects(choice["effects"])

        # Generate narrated event description using LLM
        try:
            from llm_service import generate_event_description
            player = self.state["player"]
            # Determine if there's an NPC involved
            npc_name = None
            event_id = event.get("id", "")
            choice_effects = choice.get("effects", {})
            # Check effects for NPC references
            for field in ("affinity", "trust"):
                npc_refs = choice_effects.get(field, {})
                if npc_refs:
                    for npc_id in npc_refs:
                        npc = self._npc(npc_id)
                        npc_name = npc.get("name", npc_id)
                        break
            narrated = generate_event_description(
                event_title=event.get("title", ""),
                event_text=choice.get("label", ""),
                player_name=player.get("name", "Player"),
                location=player.get("location", "Riverton"),
                npc_name=npc_name,
            )
            self._memory(narrated, tags=[event_id, choice_id], importance=2)
            self._log("INFO", f"Narrated event: {narrated[:80]}...", "Narration")
        except Exception:
            self._memory(f"{event['title']}: {choice['label']}.")

        self._log("EVENT", f"Random choice: {event.get('title', 'Unknown')} - {choice['label']}")
        self.state["seen_random_events"].append(event["id"])
        self.state["active_random_event"] = None
        self._save()
        return self.public_state()

    def public_state(self) -> dict[str, Any]:
        self._require_state()
        response = normalize_state(self.state)
        if self._is_world_pack_game():
            pack = self._active_world_pack()
            profile = deepcopy(self._naruto_profile())
            world = deepcopy(self.state.get("world", {}))
            village = profile.get("village", {})
            response.update({
                "season": "Annual cycle",
                "event": None,
                "opportunities": [],
                "outcome": None,
                "season_summary": None,
                "all_locations": {
                    place.get("id"): place.get("name", place.get("id", "Place"))
                    for place in pack.get("people", {}).get("places", [])
                },
                "dynamic_locations": {},
                "starting_scenario": "",
                "starting_map": {},
                "narration_context": {},
                "life_actions": [],
                "life_stage": self.state.get("player", {}).get("life_stage"),
                "menu_slots": pack.get("ui", {}).get("navigation", []),
                "dashboard": {"brand": pack["manifest"]["name"]},
                "current_encounter": None,
                "careers": {},
                "available_jobs": [],
                "world_state": world,
                "world_phase": world.get("phase", "academy preparation"),
                "world_pack": {
                    "id": pack["manifest"]["id"],
                    "name": pack["manifest"]["name"],
                    "version": pack["manifest"]["version"],
                    "ui": pack.get("ui", {}),
                },
                "world_actions": self._world_actions(),
                "world_people": self._world_people(),
                "world_places": self._world_places(pack),
                "world_location": self.state.get("player", {}).get("location", "home"),
                "world_people_present": [
                    person for person in self._world_people()
                    if self._world_person_is_here(person)
                ],
                "world_regions": self._world_region_state(pack),
                "world_encounter": deepcopy(world.get("active_encounter")),
                "world_combat": deepcopy(world.get("combat")),
                "world_last_combat": deepcopy(world.get("last_combat")),
                "world_combat_opponents": [
                    {key: deepcopy(value) for key, value in item.items() if key != "rewards"}
                    for item in pack.get("combat", {}).get("opponents", [])
                ],
                "world_quests": deepcopy(world.get("quests", [])),
                "world_opportunities": deepcopy(world.get("opportunities_pending", [])),
                "world_last_chat": deepcopy(world.get("last_chat")),
                "world_lore": deepcopy(pack.get("lore", {}).get("entries", [])),
                "world_organizations": [
                    {**deepcopy(item), **deepcopy(world.get("organizations", {}).get(item.get("id"), {}))}
                    for item in pack.get("organizations", {}).get("organizations", [])
                ] + deepcopy(world.get("founded_entities", [])),
                "world_title": world.get("title", "Unproven"),
                "world_influence": int(world.get("influence", 0)),
                "world_chronicle": deepcopy(world.get("chronicle", [])),
                "world_skill_trees": self._world_skill_trees_state(),
                "recommended_world_actions": self._recommended_world_actions(),
                "world_last_action_result": deepcopy(world.get("last_action_result")),
                "world_last_narration": world.get("last_narration", ""),
                "world_nature_ceremony": deepcopy(world.get("nature_ceremony")),
                "effective_attributes": self._effective_attributes(profile),
                "power_level": self._combat_power(profile),
                "world_last_forge": deepcopy(world.get("last_forge")),
                "world_legacy": deepcopy(world.get("legacy", {"generation": 1, "generations": [], "heirs": []})),
                "world_skill_ranks": {
                    key: self._skill_rank(int(value)) for key, value in profile.get("skills", {}).items()
                },
                "effective_skills": self._effective_skills(profile),
                "chakra_current": int(profile.get("chakra_current", 0)),
                "chakra_capacity": int(profile.get("attributes", {}).get("chakra_capacity", 0)),
                "world_interactions": [
                    {key: value for key, value in item.items() if key not in {"relationship_effects", "effects", "memory"}}
                    for item in pack.get("people", {}).get("interactions", [])
                ],
                "world_shop": self._world_shop_state(pack),
                "world_wallet": int(response.get("player", {}).get("stats", {}).get("money", 0)),
                "world_careers": self._world_career_state(pack),
                "training_unlocks": self._training_unlocks(),
                "action_budget": deepcopy(self.state.get("action_budget", get_action_budget(response["player"].get("age", 0)))),
                "personal_actions_remaining": self.state.get("personal_actions_remaining", 0),
                "social_actions_remaining": self.state.get("social_actions_remaining", 0),
                "naruto": profile,
                "combat_power": self._combat_power(profile),
            })
            return response
        response["season"] = SEASONS[min(self.state["season_index"], len(SEASONS) - 1)]
        response["event"] = self._current_event()
        response["opportunities"] = self._opportunities()
        response["outcome"] = self._outcome() if self.state["completed"] else None
        response["season_summary"] = self.state.get("season_summary")
        # Include all available locations (base + dynamic)
        all_locations = dict(BASE_LOCATIONS)
        if self.state.get("dynamic_locations"):
            for loc_id, loc_desc in self.state["dynamic_locations"].items():
                if loc_id not in all_locations:
                    all_locations[loc_id] = loc_desc.split(" - ")[0] if " - " in loc_desc else loc_desc
        if self.state.get("education", {}).get("school_unlocked"):
            all_locations.setdefault("school", "School")
        response["all_locations"] = all_locations
        response["dynamic_locations"] = self.state.get("dynamic_locations", {})
        response["starting_scenario"] = self.state.get("starting_scenario", "")
        response["starting_map"] = self.state.get("starting_map", {})
        response["narration_context"] = build_narration_context(response)
        response["life_actions"] = self._life_actions()
        response["life_stage"] = self.state.get("player", {}).get("life_stage")
        response["menu_slots"] = get_menu_slots(self.state.get("player", {}).get("era", "modern"))
        response["dashboard"] = get_dashboard_profile(self.state.get("player", {}).get("era", "modern"))
        response["current_encounter"] = self._current_encounter()
        # V1 additions: career, jobs, world state
        response["careers"] = get_career_summary(self.state)
        response["available_jobs"] = get_available_jobs(self.state)
        response["world_state"] = get_world_state(self.state)
        response["world_phase"] = check_world_phase(self.state)
        return response

    def _world_region_state(self, pack: dict[str, Any]) -> list[dict[str, Any]]:
        """Expose only map presentation and current route availability."""
        world = self.state.get("world", {})
        current_id = world.get("current_region")
        regions = []
        for region in pack.get("regions", {}).get("regions", []):
            item = deepcopy(region)
            item["local_state"] = deepcopy(world.get("region_state", {}).get(region.get("id"), {"security": 50, "prosperity": 50, "public_trust": 50}))
            item["current"] = item.get("id") == current_id
            item["reachable"] = item["current"] or item.get("id") in next(
                (entry.get("routes", []) for entry in pack.get("regions", {}).get("regions", []) if entry.get("id") == current_id), []
            )
            item.pop("encounters", None)
            regions.append(item)
        return regions

    @staticmethod
    def _skill_rank(level: int) -> str:
        if level >= 90:
            return "Master"
        if level >= 70:
            return "Expert"
        if level >= 45:
            return "Advanced"
        if level >= 20:
            return "Intermediate"
        return "Beginner"

    def _world_career_state(self, pack: dict[str, Any]) -> dict[str, Any]:
        profile = self._naruto_profile()
        active = profile.get("career", {})
        job_id = active.get("job_id")
        jobs = []
        age = int(self.state.get("player", {}).get("age", 0))
        rank = self.state.get("world", {}).get("rank", "Academy Student")
        rank_order = {"Academy Student": 0, "Genin": 1, "Chunin": 2, "Jonin": 3}
        for item in pack.get("careers", {}).get("jobs", []):
            candidate = deepcopy(item)
            candidate["pay"] = self._regional_economy_value(int(item.get("pay", 0)), item.get("location"), pack)
            reason = None
            qualified = True
            if active.get("job_id"):
                reason = "You already hold a position."
                qualified = False
            elif age < int(item.get("min_age", 0)):
                reason = f"Available at age {item['min_age']}."
                qualified = False
            elif self._world_requirement_reason(item.get("requirements", {})):
                reason = self._world_requirement_reason(item.get("requirements", {}))
                qualified = False
            elif rank_order.get(rank, 0) < rank_order.get(item.get("min_rank"), 0):
                reason = f"Requires {item.get('min_rank')} rank."
                qualified = False
            elif self.state.get("player", {}).get("location") != item.get("application_location", item.get("location")):
                reason = f"Ask about work at {item.get('application_location', item.get('location', '')).replace('_', ' ').title()}."
            candidate["qualified"] = qualified
            candidate["available"] = reason is None
            candidate["lock_reason"] = reason
            jobs.append(candidate)
        return {"active": deepcopy(active), "jobs": jobs, "workplace_here": bool(job_id and next((item.get("location") == self.state['player'].get('location') for item in jobs if item.get('id') == job_id), False))}

    def _regional_economy_value(self, base_value: int, location_id: str | None, pack: dict[str, Any]) -> int:
        place = next((item for item in self._world_places(pack) if item.get("id") == location_id), {})
        region_id = place.get("region_id", self.state.get("world", {}).get("current_region"))
        prosperity = max(0, min(100, int(self.state.get("world", {}).get("region_state", {}).get(region_id, {}).get("prosperity", 50))))
        multiplier = max(0.8, min(1.2, 1 + (prosperity - 50) / 250))
        return max(0, int(round(base_value * multiplier)))

    def _market_price(self, item: dict[str, Any], shop: dict[str, Any], pack: dict[str, Any]) -> int:
        base_price = max(0, int(item.get("price", 0)))
        place = next((entry for entry in self._world_places(pack) if entry.get("id") == shop.get("location")), {})
        region_id = place.get("region_id", self.state.get("world", {}).get("current_region"))
        prosperity = int(self.state.get("world", {}).get("region_state", {}).get(region_id, {}).get("prosperity", 50))
        multiplier = max(0.8, min(1.2, 1 - (prosperity - 50) / 250))
        return max(0, int(round(base_price * multiplier)))

    def _world_shop_state(self, pack: dict[str, Any]) -> dict[str, Any]:
        shop = self._active_region_shop(pack)
        for item in shop.get("items", []):
            item["base_price"] = int(item.get("price", 0))
            item["price"] = self._market_price(item, shop, pack)
        place = next((entry for entry in self._world_places(pack) if entry.get("id") == shop.get("location")), {})
        region_id = place.get("region_id", self.state.get("world", {}).get("current_region"))
        prosperity = int(self.state.get("world", {}).get("region_state", {}).get(region_id, {}).get("prosperity", 50))
        shop["economy"] = {"region_id": region_id, "prosperity": prosperity}
        return shop

    def _require_state(self) -> None:
        if self.state is None:
            raise GameRuleError("Start or load a game first.")

    def _npc(self, npc_id: str) -> dict[str, Any]:
        return next(npc for npc in self.state["npcs"] if npc["id"] == npc_id)

    def _apply_effects(self, effects: dict[str, Any]) -> None:
        for stat in ("energy", "money", "skill", "reputation"):
            if stat in effects:
                old_val = self.state["player"]["stats"][stat]
                self.state["player"]["stats"][stat] = max(0, self.state["player"]["stats"][stat] + effects[stat])
                new_val = self.state["player"]["stats"][stat]
                if new_val != old_val:
                    self._log("INFO", f"Stat change: {stat} {old_val} -> {new_val}")
        for field in ("affinity", "trust"):
            for npc_id, change in effects.get(field, {}).items():
                npc = self._npc(npc_id)
                old_val = npc[field]
                npc[field] = max(-5, min(5, npc[field] + change))
                if npc[field] != old_val:
                    self._log("INFO", f"NPC {npc_id} {field}: {old_val} -> {npc[field]}")
        new_flags = effects.get("flags", {})
        if new_flags:
            self.state["flags"].update(new_flags)
            self._log("INFO", f"Flags updated: {new_flags}")
        # Education effects
        education_effects = effects.get("education", {})
        if education_effects:
            education = self.state.setdefault("education", {})
            education.update(education_effects)
            if education_effects.get("school_unlocked"):
                self._unlock_school_location()
            self._log("INFO", f"Education updated: {education_effects}")
        # World effects
        world_effects = effects.get("world_flags") or effects.get("faction_changes") or effects.get("unlocks") or effects.get("menu_swaps")
        if world_effects:
            apply_world_effects(self.state, effects)
            self._log("INFO", "World effects applied")

    def _memory(self, text: str, tags: list[str] | None = None, linked_entities: list[str] | None = None, importance: int = 1) -> None:
        """Add a memory with optional structured metadata."""
        self.state["memories"].append(text)
        self.state["memories"] = self.state["memories"][-10:]
        self._log("INFO", f"Memory: {text[:60]}...", "Memory")
        # Also store in structured memory store
        try:
            season = SEASONS[min(self.state["season_index"], len(SEASONS) - 1)]
            add_structured_memory(
                text=text,
                tags=tags or [],
                linked_entities=linked_entities or [],
                importance=importance,
                season=season,
            )
        except Exception:
            pass  # Non-critical; game continues even if structured memory fails

    def _check_npc_milestones(self) -> None:
        """Check each NPC for available arc milestones and queue their events."""
        completed = set(self.state.get("completed_milestones", []))
        for npc in self.state["npcs"]:
            npc_id = npc.get("id", "")
            milestones = get_available_milestones(
                npc_id,
                npc,
                self.state.get("flags", {}),
                completed,
            )
            for milestone in milestones:
                milestone_id = milestone["id"]
                if milestone_id not in completed:
                    completed.add(milestone_id)
                    self.state.setdefault("completed_milestones", []).append(milestone_id)
                    event = milestone.get("event", {})
                    if event:
                        # Tag the event with IDs for tracking
                        event["npc_id"] = npc_id
                        event["milestone_id"] = milestone_id
                        event["_is_milestone"] = True
                        self.state.setdefault("milestone_events_pending", []).append(event)
                        npc_name = npc.get("name", npc_id)
                        self._log("EVENT", f"NPC milestone: {milestone['title']} for {npc_name}")
                        self._memory(
                            f"A new chapter with {npc_name}.",
                            tags=[npc_id, "milestone"],
                            linked_entities=[npc_id],
                            importance=3,
                        )

    def _save(self) -> None:
        self.save_file.parent.mkdir(exist_ok=True)
        self._write_split_state()
        self._log("INFO", "Game saved", "Save")

    def _write_split_state(self) -> None:
        if self._game_folder is None:
            self.save_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            return
        folder = self._game_folder
        player_state = {
            "player": self.state.get("player", {}),
            "origin": self.state.get("origin", {}),
        }
        world_state = {
            "npcs": self.state.get("npcs", []),
            "flags": self.state.get("flags", {}),
            "dynamic_locations": self.state.get("dynamic_locations", {}),
            "dynamic_npcs": self.state.get("dynamic_npcs", []),
            "starting_map": self.state.get("starting_map", {}),
            "starting_scenario": self.state.get("starting_scenario", ""),
            "world": self.state.get("world", {}),
            "parents": self.state.get("parents", {}),
        }
        progression_state = {
            "year": self.state.get("year", 1),
            "season_index": self.state.get("season_index", 0),
            "actions_remaining": self.state.get("actions_remaining", 3),
            "action_budget": self.state.get("action_budget", {}),
            "personal_actions_remaining": self.state.get("personal_actions_remaining"),
            "social_actions_remaining": self.state.get("social_actions_remaining"),
            "completed": self.state.get("completed", False),
            "completed_milestones": self.state.get("completed_milestones", []),
            "milestone_events_pending": self.state.get("milestone_events_pending", []),
            "seen_random_events": self.state.get("seen_random_events", []),
            "active_random_event": self.state.get("active_random_event"),
            "random_seen_this_season": self.state.get("random_seen_this_season", False),
            "education": self.state.get("education", {}),
            "career_tracks": self.state.get("career_tracks", {}),
        }
        narrative_state = {
            "memories": self.state.get("memories", []),
            "season_summary": self.state.get("season_summary", ""),
            "starting_scenario": self.state.get("starting_scenario", ""),
            "narration_context": build_narration_context(self.state),
        }
        meta_state = {
            "game_folder": self.state.get("game_folder", folder.name),
            "version": 2,
            "format": "riverton-save-v2",
            "world_pack": self.state.get("world", {}).get("pack_id"),
            "world_pack_version": self.state.get("world", {}).get("pack_version"),
        }
        game_config.write_game_json(folder, game_config.CHARACTER_FILE, player_state)
        game_config.write_game_json(folder, "world.json", world_state)
        game_config.write_game_json(folder, game_config.MAP_FILE, world_state.get("starting_map", {}))
        game_config.write_game_json(folder, game_config.NPCS_FILE, world_state.get("npcs", []))
        game_config.write_game_json(folder, game_config.EVENTS_FILE, {
            "main_events": MAIN_EVENTS,
            "random_events": RANDOM_EVENTS,
        })
        game_config.write_game_json(folder, "progression.json", progression_state)
        game_config.write_game_json(folder, "narrative.json", narrative_state)
        game_config.write_game_json(folder, "meta.json", meta_state)
        game_config.write_game_json(folder, "save_state.json", meta_state)

    def _load_split_state(self, manifest: dict[str, Any]) -> dict[str, Any]:
        folder = self._game_folder
        assert folder is not None
        character = game_config.read_game_json(folder, game_config.CHARACTER_FILE, {})
        world = game_config.read_game_json(folder, "world.json", {})
        progression = game_config.read_game_json(folder, "progression.json", {})
        narrative = game_config.read_game_json(folder, "narrative.json", {})
        state = {
            "player": character.get("player", {}),
            "origin": character.get("origin", {}),
            "year": progression.get("year", 1),
            "season_index": progression.get("season_index", 0),
            "actions_remaining": progression.get("actions_remaining", 3),
            "action_budget": progression.get("action_budget", {}),
            "personal_actions_remaining": progression.get("personal_actions_remaining"),
            "social_actions_remaining": progression.get("social_actions_remaining"),
            "npcs": world.get("npcs", []) if isinstance(world, dict) else [],
            "flags": world.get("flags", {}) if isinstance(world, dict) else {},
            "memories": narrative.get("memories", []),
            "active_random_event": progression.get("active_random_event"),
            "random_seen_this_season": progression.get("random_seen_this_season", False),
            "seen_random_events": progression.get("seen_random_events", []),
            "completed": progression.get("completed", False),
            "completed_milestones": progression.get("completed_milestones", []),
            "milestone_events_pending": progression.get("milestone_events_pending", []),
            "dynamic_locations": world.get("dynamic_locations", {}) if isinstance(world, dict) else {},
            "dynamic_npcs": world.get("dynamic_npcs", []) if isinstance(world, dict) else [],
            "starting_scenario": narrative.get("starting_scenario", ""),
            "starting_map": game_config.read_game_json(folder, game_config.MAP_FILE, {}),
            "game_folder": manifest.get("game_folder", folder.name),
            "education": progression.get("education", {}),
            "career_tracks": progression.get("career_tracks", {}),
            "parents": world.get("parents", {"strictness": 0.5, "support": 0.5, "name": "Parents"}) if isinstance(world, dict) else {"strictness": 0.5, "support": 0.5, "name": "Parents"},
            "world": world.get("world", {"era": normalize_era(character.get("player", {}).get("era")), "phase": "baseline", "unlocks": {}}) if isinstance(world, dict) else {"era": normalize_era(character.get("player", {}).get("era")), "phase": "baseline", "unlocks": {}},
        }
        state.setdefault("flags", {})
        return normalize_state(state)

    def _current_event(self) -> dict[str, Any] | None:
        index = self.state["season_index"]
        if index >= len(MAIN_EVENTS):
            return None
        base_event = deepcopy(MAIN_EVENTS[index])
        # Conditional seasonal main events: add choices based on player state
        stats = self.state["player"]["stats"]
        flags = self.state["flags"]
        origin_id = self.state.get("origin", {}).get("id", "")

        # Add origin-specific choices for the first event
        if index == 0 and origin_id:
            if origin_id == "scholarship_student":
                base_event["choices"].append({
                    "id": "scholar_tutoring",
                    "label": "Offer tutoring at the college",
                    "text": "Use your academic momentum to help others and earn a small stipend.",
                    "effects": {"money": 1, "skill": 1, "reputation": 1, "energy": -1, "flags": {"tutoring": True}},
                })
            elif origin_id == "cafe_worker":
                base_event["choices"].append({
                    "id": "cafe_network",
                    "label": "Network at the cafe",
                    "text": "Use your cafe connections to learn about local opportunities.",
                    "effects": {"reputation": 1, "money": 1, "trust": {"priya": 1}, "flags": {"cafe_network": True}},
                })
            elif origin_id == "local_resident":
                base_event["choices"].append({
                    "id": "community_roots",
                    "label": "Reconnect with old contacts",
                    "text": "Your history in Riverton opens doors others can't see.",
                    "effects": {"reputation": 2, "trust": {"sam": 1}, "flags": {"roots_activated": True}},
                })

        # Add stat-dependent choices for later events
        if index >= 1 and stats.get("skill", 0) >= 2:
            base_event["choices"].append({
                "id": "advanced_study",
                "label": "Pursue advanced study",
                "text": "Your growing skill opens access to more challenging material.",
                "effects": {"skill": 2, "energy": -2, "flags": {"advanced_study": True}},
            })
        if index >= 2 and stats.get("reputation", 0) >= 3:
            base_event["choices"].append({
                "id": "public_endorsement",
                "label": "Seek a public endorsement",
                "text": "Use your reputation to get a formal endorsement from a community leader.",
                "effects": {"reputation": 2, "trust": {"sam": 1}, "flags": {"endorsed": True}},
            })

        # Limit choices to a reasonable number and add LLM options
        base_event["choices"] = base_event["choices"][:4]
        options = get_dynamic_year_options(self._llm_context())
        # Merge LLM options with deterministic choices
        llm_choices = [
            {
                "id": option["id"],
                "label": option["label"],
                "text": option.get("description", "Choose this response."),
                "effects": option.get("effects", {}),
            }
            for option in options[:2]  # Limit to 2 LLM options
        ]
        # Combine: deterministic choices first, then LLM options
        combined = base_event["choices"] + llm_choices
        # Deduplicate by id
        seen_ids = set()
        unique_choices = []
        for choice in combined:
            if choice["id"] not in seen_ids:
                seen_ids.add(choice["id"])
                unique_choices.append(choice)
        base_event["choices"] = unique_choices[:6]  # Max 6 choices
        return base_event

    def _llm_context(self) -> dict[str, Any]:
        return {
            "player": deepcopy(self.state["player"]),
            "npcs": deepcopy(self.state["npcs"]),
            "flags": deepcopy(self.state["flags"]),
            "life_actions": self._life_actions(),
            "menu_slots": get_menu_slots(self.state.get("player", {}).get("era", "modern")),
            "world": deepcopy(self.state.get("world", {})),
        }

    def _advance_age(self, years: int) -> None:
        player = self.state.get("player", {})
        current_age = int(player.get("age", 18))
        player["age"] = max(0, current_age + years)
        player["life_stage"] = self._life_stage(player["age"])
        self._advance_school_progress()
        if self._should_prompt_school_encounter():
            encounter = self._build_school_encounter(player["age"])
            self.state["encounters"] = [encounter]
        # Check for age-based events from era data
        self._check_age_events()

    def _check_age_events(self) -> None:
        """Check for age-triggered events from the era data loader."""
        if self.state.get("encounters"):
            return
        player = self.state.get("player", {})
        age = int(player.get("age", 18))
        era = player.get("era", "modern")
        loader = get_era_loader(era)
        events = loader.get_age_events(min_age=age, max_age=age)
        if not events:
            return
        # Filter by requirements
        eligible = []
        for event in events:
            reqs = event.get("requires", {})
            if self._meets_requirements(reqs):
                eligible.append(event)
        if eligible:
            # Use Event Director to pick the best one
            context = self._llm_context()
            selected = select_event(eligible, context, recent_ids=set(self.state.get("seen_random_events", [])))
            if selected:
                self.state["encounters"] = [selected]
                self._log("EVENT", f"Age event triggered: {selected.get('title', 'Unknown')}")

    @staticmethod
    def _life_stage(age: int) -> str:
        return get_life_stage(age)

    def _life_actions(self) -> list[dict[str, Any]]:
        player = self.state.get("player", {})
        stats = player.get("stats", {})
        flags = self.state.get("flags", {})
        age = int(player.get("age", 18))
        actions: list[dict[str, Any]] = [
            {"id": "work", "label": "Work", "category": "career", "description": "Earn money and build experience.", "effects": {"money": 1, "energy": -1}},
            {"id": "rest", "label": "Rest", "category": "health", "description": "Recover energy and keep going.", "effects": {"energy": 2, "money": -1}},
            {"id": "socialize", "label": "Socialize", "category": "relationships", "description": "Raise reputation and build ties.", "effects": {"reputation": 1, "energy": -1}},
        ]
        if self.state.get("education", {}).get("school_unlocked"):
            actions.append({"id": "school", "label": "School", "category": "education", "description": "Visit the school location and advance education.", "effects": {"flags": {"school_visit": True}}})
        if age >= 16 and not self.state.get("education", {}).get("school_unlocked"):
            actions.append({"id": "date", "label": "Date", "category": "relationships", "description": "Explore romantic relationships.", "effects": {"reputation": 1, "energy": -1}})
        if age >= 18:
            actions.append({"id": "travel", "label": "Travel", "category": "lifestyle", "description": "Visit another location for free.", "effects": {}})
        if age >= 18 and stats.get("reputation", 0) >= 1:
            actions.append({"id": "apply_job", "label": "Apply for jobs", "category": "career", "description": "Look for better work opportunities.", "effects": {"flags": {"job_hunt": True}}})
        if age >= 18 and stats.get("money", 0) <= 2:
            actions.append({"id": "crime", "label": "Take a risk", "category": "crime", "description": "Pursue a dangerous shortcut with consequences.", "effects": {"flags": {"risky_path": True}}})
        if flags.get("job_hunt"):
            actions.append({"id": "interview", "label": "Interview", "category": "career", "description": "Try to land a stable job.", "effects": {"skill": 1, "reputation": 1, "flags": {"hired": True}}})
        return actions

    def _should_prompt_school_encounter(self) -> bool:
        player = self.state.get("player", {})
        age = int(player.get("age", 18))
        education = self.state.get("education", {})
        if education.get("school_unlocked"):
            return False
        return age in {4, 5, 6, 7, 8, 13} and education.get("status") in {"none", "refused", "pending"}

    def _advance_school_progress(self) -> None:
        education = self.state.get("education", {})
        player = self.state.get("player", {})
        if not education.get("school_unlocked"):
            return
        age = int(player.get("age", 18))
        if age < 5:
            return
        if education.get("status") not in {"enrolled", "forced", "hybrid"}:
            return
        attendance = int(education.get("attendance", 0)) + 1
        level = int(education.get("level", 0)) + 1
        grade = education.get("grade", "C")
        if attendance >= 3 and grade != "A":
            grade = "B" if grade == "C" else "A"
        if attendance >= 5:
            self._complete_school_cycle(education, level, grade)
            return
        education.update({"attendance": attendance, "level": level, "grade": grade})
        self._maybe_school_event()

    def _complete_school_cycle(self, education: dict[str, Any], level: int, grade: str) -> None:
        education.update({"attendance": 0, "level": level, "grade": grade, "status": "graduated"})
        self.state.setdefault("flags", {})["school_graduated"] = True
        self.state.setdefault("memories", []).append("You completed a school cycle.")
        self._memory("You completed a school cycle.", tags=["school", "graduation"], importance=3)
        self.state["encounters"] = [{
            "id": "school_graduation",
            "type": "education",
            "title": "School milestone reached",
            "text": "You have reached a major point in your school path.",
            "choices": [
                {"id": "continue", "label": "Continue onward", "text": "Keep moving forward."},
                {"id": "focus_career", "label": "Focus on career", "text": "Shift attention to work and future paths."},
            ],
        }]

    def _maybe_school_event(self) -> None:
        education = self.state.get("education", {})
        if not education.get("school_unlocked"):
            return
        if self.state.get("encounters"):
            return
        if education.get("status") not in {"enrolled", "forced", "hybrid"}:
            return
        if education.get("attendance", 0) % 2 != 0:
            return
        self.state["encounters"] = [self._build_school_event()]

    def _build_school_event(self) -> dict[str, Any]:
        return {
            "id": "school_day_event",
            "type": "school_day",
            "title": "A day at school",
            "text": "School has a small decision waiting inside it.",
            "choices": [
                {"id": "study_hard", "label": "Study hard", "text": "Put energy into grades.", "effects": {"skill": 1, "reputation": 1}},
                {"id": "join_activity", "label": "Join an activity", "text": "Get involved in something extra.", "effects": {"reputation": 1, "flags": {"school_activity": True}}},
                {"id": "skip_class", "label": "Skip class", "text": "Take a risk and drift.", "effects": {"energy": 1, "reputation": -1, "flags": {"school_skipped": True}}},
            ],
        }

    def _resolve_school_day(self, choice_id: str, encounter: dict[str, Any]) -> None:
        if choice_id == "study_hard":
            education = self.state.get("education", {})
            education["grade"] = "A" if education.get("grade") == "B" else "B"
            education["attendance"] = int(education.get("attendance", 0)) + 1
            self._memory("You studied hard at school.", tags=["school", "study"], importance=2)
            return
        if choice_id == "join_activity":
            education = self.state.get("education", {})
            activities = education.setdefault("extracurriculars", [])
            if "activity" not in activities:
                activities.append("activity")
            self.state["flags"]["school_activity"] = True
            self._memory("You joined a school activity.", tags=["school", "activity"], importance=2)
            return
        if choice_id == "skip_class":
            education = self.state.get("education", {})
            education["grade"] = "C" if education.get("grade") == "A" else "D"
            education["attendance"] = max(0, int(education.get("attendance", 0)) - 1)
            self.state["flags"]["school_skipped"] = True
            self._memory("You skipped class.", tags=["school", "skip"], importance=2)

    def _resolve_school_graduation(self, choice_id: str, encounter: dict[str, Any]) -> None:
        education = self.state.get("education", {})
        if choice_id == "continue":
            education["status"] = "post_school"
            education["school_unlocked"] = False
            education["location"] = None
            self.state["flags"]["post_school"] = True
            self._memory("You moved beyond the school path.", tags=["school", "post"], importance=3)
            return
        if choice_id == "focus_career":
            education["status"] = "career_focus"
            education["school_unlocked"] = False
            education["location"] = None
            self.state["flags"]["career_focus"] = True
            self._memory("You shifted from school toward work.", tags=["school", "career"], importance=3)

    def _init_parent_state(self, origin_id: str) -> None:
        strictness = 0.5
        support = 0.5
        guardian_name = "Parents"
        guardian_style = "balanced"
        if origin_id == "scholarship_student":
            strictness = 0.75
            support = 0.45
            guardian_style = "strict"
        elif origin_id == "cafe_worker":
            strictness = 0.55
            support = 0.6
            guardian_style = "supportive"
        elif origin_id == "local_resident":
            strictness = 0.65
            support = 0.5
            guardian_style = "practical"
        self.state["parents"] = {
            "strictness": strictness,
            "support": support,
            "name": guardian_name,
            "style": guardian_style,
            "memory": [],
        }

    def _ensure_progression_defaults(self) -> None:
        self.state.setdefault("parents", {"strictness": 0.5, "support": 0.5, "name": "Parents", "style": "balanced", "memory": []})
        self.state.setdefault("education", {"status": "none", "location": None, "forced": False, "school_unlocked": False})
        self.state.setdefault("encounters", [])
        self.state.setdefault("world", {"era": normalize_era(self.state.get("player", {}).get("era")), "phase": "baseline", "unlocks": {}})
        if self._is_world_pack_game():
            self._naruto_profile()
            self._migrate_world_pack_state()
            budget = get_action_budget(self.state.get("player", {}).get("age", 0))
            self.state.setdefault("action_budget", budget)
            if not isinstance(self.state.get("personal_actions_remaining"), int):
                self.state["personal_actions_remaining"] = budget["personal"]
            if not isinstance(self.state.get("social_actions_remaining"), int):
                self.state["social_actions_remaining"] = budget["social"]
            self.state["actions_remaining"] = (
                self.state["personal_actions_remaining"] + self.state["social_actions_remaining"]
            )
            self._refresh_world_pack_unlocks()

    def _migrate_world_pack_state(self) -> None:
        """Fill new pack fields and characters when opening an older save."""
        pack = self._active_world_pack()
        world = self.state.setdefault("world", {})
        profile = self._naruto_profile()
        regions = pack.get("regions", {}).get("regions", [])
        region_ids = {item.get("id") for item in regions}
        village_id = profile.get("village", {}).get("id", world.get("village", "leaf"))
        start_regions = pack.get("regions", {}).get("start_region_by_village", {})
        current_region = world.get("current_region")
        if current_region not in region_ids:
            current_region = start_regions.get(village_id) or (regions[0].get("id") if regions else None)
        world["current_region"] = current_region
        home_region = world.get("home_region")
        if home_region not in region_ids:
            home_region = start_regions.get(village_id) or current_region
        world["home_region"] = home_region
        world.setdefault("village", village_id)
        if not isinstance(world.get("region_state"), dict):
            world["region_state"] = {}
        for region in regions:
            region_id = region.get("id")
            local = world["region_state"].get(region_id)
            if not isinstance(local, dict):
                local = {}
                world["region_state"][region_id] = local
            for key, default in (("security", 52), ("prosperity", 48), ("public_trust", 50)):
                local.setdefault(key, default)
        for key in ("encounters_seen_this_year", "action_counts"):
            if not isinstance(world.get(key), dict):
                world[key] = {}
        for key in ("opportunities_seen", "opportunities_pending", "opportunities_resolved", "quests", "chronicle"):
            if not isinstance(world.get(key), list):
                world[key] = []
        if not isinstance(world.get("active_encounter"), (dict, type(None))):
            world["active_encounter"] = None
        if not isinstance(world.get("combat"), (dict, type(None))):
            world["combat"] = None
        if not isinstance(world.get("organizations"), dict):
            world["organizations"] = {}
        if not isinstance(world.get("legacy"), dict):
            world["legacy"] = {"generation": 1, "generations": [], "heirs": []}
        world["legacy"].setdefault("generation", 1)
        world["legacy"].setdefault("generations", [])
        world["legacy"].setdefault("heirs", [])
        for organization in pack.get("organizations", {}).get("organizations", []):
            organization_id = organization.get("id")
            progress = world["organizations"].get(organization_id)
            if not isinstance(progress, dict):
                progress = {}
                world["organizations"][organization_id] = progress
            progress.setdefault("influence", 0)
            progress.setdefault("level", 0)
        world["pack_version"] = pack.get("manifest", {}).get("version", world.get("pack_version", 1))

        npcs = self.state.setdefault("npcs", [])
        existing_ids = {item.get("id") for item in npcs}
        pack_people = {item.get("id"): item for item in pack.get("people", {}).get("people", [])}
        for npc in npcs:
            template = pack_people.get(npc.get("id"), {})
            if npc.get("role") == "Parent":
                npc["region_id"] = home_region
            if npc.get("role") == "Blacksmith":
                npc["region_id"] = current_region
                npc["local_location"] = "blacksmith"
            for key in ("region_id", "local_location"):
                if key in template and npc.get("role") not in {"Parent", "Blacksmith"}:
                    npc[key] = template[key]
            if template.get("region_id"):
                # Pack anchors migrate legacy base-place IDs to stable regional IDs.
                npc["location"] = template.get("location", npc.get("location", "unknown"))
            if not isinstance(npc.get("memories"), list):
                npc["memories"] = []
            if not isinstance(npc.get("interaction_counts"), dict):
                npc["interaction_counts"] = {}
            if not isinstance(npc.get("chat_history"), list):
                npc["chat_history"] = []
        age = int(self.state.get("player", {}).get("age", 0))
        for person in pack.get("people", {}).get("people", []):
            if person.get("id") in existing_ids:
                continue
            npc = deepcopy(person)
            if npc.get("role") == "Academy peer":
                npc["age"] = age
            elif npc.get("role") == "Parent":
                npc["age"] = max(24, age + 24)
            elif "instructor" in str(npc.get("role", "")).lower():
                npc["age"] = max(22, age + 15)
            npc["memories"] = list(npc.get("memories", []))[-20:]
            npc["interaction_counts"] = {}
            npc["reaction"] = self._npc_reaction(npc)
            npcs.append(npc)

    def _current_encounter(self) -> dict[str, Any] | None:
        player = self.state.get("player", {})
        age = int(player.get("age", 18))
        education = self.state.get("education", {})
        pending = self.state.get("encounters", [])
        if pending:
            return pending[-1]
        if age < 8 and education.get("status") in {"none", "pending"}:
            return self._build_school_encounter(age)
        if age == 13 and not education.get("school_unlocked"):
            return self._build_school_encounter(age)
        if age == 13 and education.get("school_unlocked"):
            return self._build_teen_encounter()
        return None

    def _build_school_encounter(self, age: int) -> dict[str, Any]:
        parents = self.state.get("parents", {"strictness": 0.5, "support": 0.5})
        return {
            "id": f"school_age_{age}",
            "type": "education",
            "title": "Your parents ask about school",
            "text": "They want to know whether you will go to school.",
            "choices": [
                {"id": "yes_school", "label": "Yes, go to school", "text": "Agree to attend school."},
                {"id": "no_school", "label": "No, stay home", "text": "Refuse the school path."},
            ],
            "parents": parents,
            "forced": parents.get("strictness", 0.5) >= 0.7,
        }

    def _build_teen_encounter(self) -> dict[str, Any]:
        parents = self.state.get("parents", {"strictness": 0.5, "support": 0.5, "style": "balanced"})
        education = self.state.get("education", {})
        return {
            "id": "teen_decision",
            "type": "education",
            "title": "Teenage pressure builds",
            "text": "Your family wants to know what comes next: stay on the school path, look for work, or drift into your own thing.",
            "choices": [
                {"id": "keep_school", "label": "Stay in school", "text": "Commit to education."},
                {"id": "part_time", "label": "Take a part-time path", "text": "Balance school and responsibility."},
                {"id": "push_back", "label": "Push back", "text": "Try to define your own path."},
            ],
            "parents": parents,
            "school": education,
        }

    def _resolve_education_encounter(self, choice_id: str, encounter: dict[str, Any]) -> None:
        parents = encounter.get("parents", self.state.get("parents", {}))
        forced = bool(encounter.get("forced"))
        if forced or (choice_id == "yes_school"):
            self._unlock_school_location()
            self.state["education"] = {"status": "enrolled", "location": "school", "forced": forced, "school_unlocked": True}
            self.state["flags"]["school_path"] = True
            self._memory("School became part of your life.", tags=["school", "education"], importance=2)
            return
        if choice_id == "no_school":
            if parents.get("strictness", 0.5) >= 0.7:
                self._unlock_school_location()
                self.state["education"] = {"status": "forced", "location": "school", "forced": True, "school_unlocked": True}
                self.state["flags"]["school_forced"] = True
                self._memory("Your parents forced the school path anyway.", tags=["school", "forced"], importance=3)
            else:
                self.state["education"] = {"status": "refused", "location": None, "forced": False, "school_unlocked": False}
                self._memory("You resisted the school path.", tags=["school", "refused"], importance=2)
        if encounter.get("id") == "teen_decision":
            self._resolve_teen_encounter(choice_id, encounter)

    def _unlock_school_location(self) -> None:
        LOCATIONS["school"] = "School"

    def _resolve_teen_encounter(self, choice_id: str, encounter: dict[str, Any]) -> None:
        parents = encounter.get("parents", {})
        if choice_id == "keep_school":
            self.state["education"] = {"status": "enrolled", "location": "school", "forced": False, "school_unlocked": True}
            self.state["flags"]["teen_school_commitment"] = True
            self._memory("You chose to stay on the school path as a teen.", tags=["teen", "school"], importance=2)
            return
        if choice_id == "part_time":
            self.state["education"] = {"status": "hybrid", "location": "school", "forced": False, "school_unlocked": True}
            self.state["flags"]["teen_part_time"] = True
            self._memory("You split your attention between school and responsibility.", tags=["teen", "hybrid"], importance=2)
            return
        if choice_id == "push_back":
            if parents.get("strictness", 0.5) >= 0.7:
                self._unlock_school_location()
                self.state["education"] = {"status": "forced", "location": "school", "forced": True, "school_unlocked": True}
                self.state["flags"]["teen_forced_back"] = True
                self._memory("Your parents pushed you back onto the school path.", tags=["teen", "forced"], importance=3)
            else:
                self.state["education"] = {"status": "independent", "location": None, "forced": False, "school_unlocked": False}
                self.state["flags"]["teen_independent"] = True
                self._memory("You pushed for your own path.", tags=["teen", "independent"], importance=2)

    def _meets_requirements(self, requirements: dict[str, Any]) -> bool:
        if requirements.get("location") and self.state["player"]["location"] != requirements["location"]:
            return False
        for stat, minimum in requirements.get("stat", {}).items():
            if self.state["player"]["stats"][stat] < minimum:
                return False
        for npc_id, values in requirements.get("npc", {}).items():
            npc = self._npc(npc_id)
            if any(npc[field] < minimum for field, minimum in values.items()):
                return False
        # Flag requirements (list format: all must be true)
        required_flags = requirements.get("flags", [])
        if isinstance(required_flags, list):
            for flag in required_flags:
                if not self.state.get("flags", {}).get(flag):
                    return False
        elif isinstance(required_flags, dict):
            for flag, value in required_flags.items():
                if self.state.get("flags", {}).get(flag) != value:
                    return False
        # Money requirement
        if "money" in requirements and self.state["player"]["stats"].get("money", 0) < requirements["money"]:
            return False
        # Age requirement
        if "age" in requirements and int(self.state["player"].get("age", 0)) < requirements["age"]:
            return False
        return True

    def _choose_random_event(self) -> dict[str, Any] | None:
        """Use Event Director to select the best eligible event."""
        pool = [event for event in RANDOM_EVENTS if event["id"] not in self.state["seen_random_events"] and self._meets_requirements(event["requires"])]
        if not pool:
            return None
        # Also consider NPC arc events
        arc_events = get_npc_arc_events(
            self.state["npcs"],
            self.state["flags"],
            set(self.state.get("completed_milestones", [])),
        )
        if arc_events:
            pool = pool + arc_events
        context = {
            "player": deepcopy(self.state["player"]),
            "npcs": deepcopy(self.state["npcs"]),
            "flags": deepcopy(self.state["flags"]),
            "origin": deepcopy(self.state.get("origin", {})),
            "seen_random_events": self.state.get("seen_random_events", []),
            "season_index": self.state.get("season_index", 0),
        }
        # Use the Event Director for deterministic scoring instead of random weighted selection
        selected = select_event(pool, context, recent_ids=set(self.state.get("seen_random_events", [])))
        self._log("EVENT", f"Event Director selected: {selected.get('title', 'Unknown') if selected else 'None'}")
        return selected if selected else (random.choices(pool, weights=[event.get("weight", 1) for event in pool], k=1)[0] if pool else None)

    def _opportunities(self) -> list[dict[str, str]]:
        stats, flags = self.state["player"]["stats"], self.state["flags"]
        results = []
        if stats["skill"] >= 2:
            results.append({"name":"Professional route", "hint":"Build skill, then earn Dr. Ellis's trust."})
        if self._npc("priya")["trust"] >= 2:
            results.append({"name":"Cafe route", "hint":"More shifts can lead to a promotion."})
        if self._npc("sam")["trust"] >= 2 or flags.get("community_focus"):
            results.append({"name":"Community route", "hint":"Campaign work can open leadership."})
        if stats["skill"] >= 3 and stats["money"] >= 5:
            results.append({"name":"Independent route", "hint":"Your resources could support your own project."})
        return results

    def _outcome(self) -> dict[str, str]:
        flags, stats = self.state["flags"], self.state["player"]["stats"]
        if flags.get("study_focus") and flags.get("portfolio") and flags.get("applied") and flags.get("interviewed") and stats["skill"] >= 4 and self._npc("dr_ellis")["trust"] >= 2:
            return {"title":"A professional door opens", "text":"Your preparation and Dr. Ellis's recommendation earn you a trainee offer."}
        if flags.get("community_focus") and flags.get("campaign") and flags.get("spoke") and flags.get("led") and stats["reputation"] >= 5 and self._npc("sam")["trust"] >= 3:
            return {"title":"A community leader emerges", "text":"The campaign asks you to take a formal leadership role."}
        if flags.get("cafe_shift") and self._npc("priya")["trust"] >= 3 and stats["money"] >= 5:
            return {"title":"Trusted with the keys", "text":"Priya offers you a permanent role and more responsibility at Juniper Cafe."}
        if stats["skill"] >= 3 and stats["money"] >= 5:
            return {"title":"Your own small beginning", "text":"With skill, savings, and nerve, you begin a small independent project."}
        return {"title":"A year of foundations", "text":"You have learned what matters to you. Another year could turn those choices into a clearer path."}
