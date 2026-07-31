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

    def new_game(self, name: str, origin_id: str, dynamic_locations: dict[str, str] | None = None, dynamic_npcs: list[dict] | None = None, generated: dict[str, Any] | None = None) -> dict[str, Any]:
        name = name.strip()
        if not name:
            self._log("ERROR", "New game failed: empty name")
            raise GameRuleError("Enter a name before beginning.")
        origin = next((item for item in ORIGINS if item["id"] == origin_id), None)
        if not origin:
            self._log("ERROR", f"New game failed: invalid origin '{origin_id}'")
            raise GameRuleError("Choose a valid origin.")

        # Create per-game folder: {player_name}_{timestamp}
        game_folder = game_config.create_game_folder(name)
        self._set_game_folder(game_folder)
        self._log("INFO", f"Created game folder: {game_folder.name}")

        self.state = {"player":{"name":name,"location":"apartment","stats":{"energy":5,"money":4,"skill":0,"reputation":0}},"origin":deepcopy(origin),"year":1,"season_index":0,"actions_remaining":3,"npcs":deepcopy(NPC_TEMPLATES),"flags":{},"memories":[],"active_random_event":None,"random_seen_this_season":False,"seen_random_events":[],"completed":False,"completed_milestones":[],"milestone_events_pending":[],"dynamic_locations":{},"dynamic_npcs":[],"starting_scenario":"","starting_map":{},"game_folder":game_folder.name}
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
        self.state = json.loads(self.save_file.read_text(encoding="utf-8"))
        self.state.setdefault("actions_remaining", 3)
        self.state.setdefault("seen_random_events", [])
        self.state.setdefault("active_random_event", None)
        self.state.setdefault("completed_milestones", [])
        self.state.setdefault("milestone_events_pending", [])
        # Restore game folder from state if present
        if self._game_folder is None and self.state.get("game_folder"):
            found = game_config.get_game_folder(self.state["player"].get("name", ""), self.state["game_folder"])
            if found:
                self._set_game_folder(found)
        # Reload structured memories from persistent store
        from memory_store import load_all_memories
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
        response = deepcopy(self.state)
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
        response["all_locations"] = all_locations
        response["dynamic_locations"] = self.state.get("dynamic_locations", {})
        response["starting_scenario"] = self.state.get("starting_scenario", "")
        response["starting_map"] = self.state.get("starting_map", {})
        return response

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
        self.save_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        self._log("INFO", "Game saved", "Save")

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
        }

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
