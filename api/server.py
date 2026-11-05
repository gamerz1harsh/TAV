"""Flask API server for Riverton - provides REST endpoints for the Electron frontend.

This server manages the GameEngine instance and serves the web UI files.
The Electron main process spawns this server as a child process and the
BrowserWindow loads the UI served from this HTTP server.

Configuration via environment variables:
  RIVERTON_PORT  - Port to listen on (default 5000)
  RIVERTON_HOST  - Host to bind (default 0.0.0.0)
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from flask import Flask, request, jsonify, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_engine import GameEngine, GameRuleError, ORIGINS, MAIN_EVENTS, RANDOM_EVENTS
from game_config import GAMES_DIR, delete_game_folder, list_games, get_save_file_for_game
from game_schema import get_menu_slots, get_dashboard_profile, normalize_era
from llm_service import check_llm_connection, load_llm_settings, save_llm_settings
from world_pack import get_world_pack, list_world_packs, WorldPackError

WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
PORT = int(os.environ.get("RIVERTON_PORT", os.environ.get("PORT", "5000")))
HOST = os.environ.get("RIVERTON_HOST", os.environ.get("HOST", "0.0.0.0"))

app = Flask(__name__, static_folder=None)


# ─── CORS ──────────────────────────────────────────────────────────────────
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# ─── Static file serving (web UI) ──────────────────────────────────────────
@app.route("/")
def serve_index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:subpath>")
def serve_static_file(subpath: str):
    # Don't serve API routes as static files
    if subpath.startswith("api/"):
        return ("Not found", 404)
    return send_from_directory(WEB_DIR, subpath)


# ─── Thread-safe game state ────────────────────────────────────────────────
_game_lock = threading.Lock()
_game_engine: Optional[GameEngine] = None
_current_game_folder: Optional[str] = None


def init_engine() -> None:
    """Initialize the game engine instance."""
    global _game_engine, _current_game_folder
    _game_engine = GameEngine()
    _current_game_folder = None


def get_engine() -> GameEngine:
    """Get the game engine instance, initializing if needed."""
    global _game_engine
    if _game_engine is None:
        init_engine()
    return _game_engine


# ─── public_state helper ───────────────────────────────────────────────────
def public_state(state: dict[str, Any]) -> dict[str, Any]:
    """Make the game engine's public state JSON-serializable for API responses.

    The engine's public_state() already returns clean dicts, but some fields
    (like Path objects or narration context) may contain non-serializable
    types. This function ensures safe JSON serialization.
    """
    def _make_serializable(obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, dict):
            return {str(k): _make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_make_serializable(v) for v in obj]
        if isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        # Fallback: convert to string
        return str(obj)

    return _make_serializable(state)


# ═══════════════════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health() -> Any:
    """Health check endpoint."""
    return jsonify({"status": "ok", "game": "anime-sim", "port": PORT})


def _world_call(method_name: str, *args: Any) -> Any:
    """Run one world-pack engine operation under the shared game lock."""
    try:
        engine = get_engine()
        with _game_lock:
            result = getattr(engine, method_name)(*args)
        return jsonify({"success": True, "state": public_state(result)})
    except GameRuleError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except Exception as error:
        app.logger.exception("World simulation request failed")
        return jsonify({"success": False, "error": f"Simulation error: {error}"}), 500


@app.route("/api/world/packs", methods=["GET"])
def world_packs() -> Any:
    try:
        packs = list_world_packs()
        payload = []
        for item in packs:
            pack = get_world_pack(item["id"])
            payload.append({
                **item,
                "creation": pack.get("character_creation", {}),
                "trait_count": len(pack.get("traits", {}).get("traits", [])),
                "region_count": len(pack.get("regions", {}).get("regions", [])),
            })
        return jsonify({"success": True, "packs": payload})
    except WorldPackError as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/world/saves", methods=["GET"])
def world_saves() -> Any:
    """List only saves that declare an installed world pack."""
    saves = []
    for game in list_games():
        if not game.get("has_save"):
            continue
        folder = GAMES_DIR / game["folder"]
        try:
            manifest = json.loads((folder / "save_state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pack_id = manifest.get("world_pack") if isinstance(manifest, dict) else None
        if pack_id:
            saves.append({**game, "world_pack": pack_id})
    return jsonify({"success": True, "games": saves[:12]})


@app.route("/api/world/new_game", methods=["POST"])
def world_new_game() -> Any:
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()[:32]
    pack_id = str(data.get("world_pack_id", "naruto")).strip().lower()
    if not name:
        return jsonify({"success": False, "error": "Choose a name for your character."}), 400
    try:
        engine = get_engine()
        with _game_lock:
            result = engine.new_game(name, "", world_pack_id=pack_id, world_options=data.get("world_options", {}))
        return jsonify({"success": True, "state": public_state(result)})
    except (GameRuleError, WorldPackError) as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except Exception as error:
        app.logger.exception("Failed to create Anime Sim life")
        return jsonify({"success": False, "error": f"Could not start the simulation: {error}"}), 500


@app.route("/api/world/action", methods=["POST"])
def world_action() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("perform_world_action", str(data.get("action_id", "")))


@app.route("/api/world/skill-tree/unlock", methods=["POST"])
def world_skill_tree_unlock() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("learn_world_skill_node", str(data.get("node_id", "")))


@app.route("/api/world/mode/toggle", methods=["POST"])
def world_mode_toggle() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("toggle_world_mode", str(data.get("mode_id", "")), bool(data.get("active", False)))


@app.route("/api/world/technique/toggle", methods=["POST"])
def world_technique_toggle() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("toggle_passive_technique", str(data.get("technique_id", "")), bool(data.get("active", False)))


@app.route("/api/world/advance", methods=["POST"])
def world_advance() -> Any:
    return _world_call("advance_world_year")


@app.route("/api/world/location", methods=["POST"])
def world_location() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("travel_world_location", str(data.get("location_id", "")))


@app.route("/api/world/region", methods=["POST"])
def world_region() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("travel_world_region", str(data.get("region_id", "")))


@app.route("/api/world/encounter", methods=["POST"])
def world_encounter() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("resolve_world_encounter", str(data.get("choice_id", "")))


@app.route("/api/world/combat/start", methods=["POST"])
def world_combat_start() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("start_world_combat", str(data.get("opponent_id", "")))


@app.route("/api/world/combat/turn", methods=["POST"])
def world_combat_turn() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("world_combat_turn", str(data.get("move_id", "")))


@app.route("/api/world/chat", methods=["POST"])
def world_chat() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("talk_to_world_npc", str(data.get("npc_id", "")), str(data.get("message", "")))


@app.route("/api/world/interact", methods=["POST"])
def world_interact() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("interact_with_world_npc", str(data.get("npc_id", "")), str(data.get("interaction_id", "")))


@app.route("/api/world/quest/accept", methods=["POST"])
def world_quest_accept() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("accept_world_quest", str(data.get("quest_id", "")))


@app.route("/api/world/quest/assign", methods=["POST"])
def world_quest_assign() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("assign_world_quest", str(data.get("quest_id", "")), str(data.get("npc_id", "")))


@app.route("/api/world/opportunity/resolve", methods=["POST"])
def world_opportunity_resolve() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call(
        "resolve_world_opportunity",
        str(data.get("opportunity_id", "")),
        str(data.get("choice_id", "")),
    )


@app.route("/api/world/shop/purchase", methods=["POST"])
def world_shop_purchase() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("purchase_world_item", str(data.get("item_id", "")))


@app.route("/api/world/equipment/equip", methods=["POST"])
def world_equipment_equip() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("equip_world_item", str(data.get("instance_id", "")))


@app.route("/api/world/equipment/forge", methods=["POST"])
def world_equipment_forge() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("forge_world_item", str(data.get("instance_id", "")))


@app.route("/api/world/legacy/family", methods=["POST"])
def world_legacy_family() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("start_world_legacy_family", str(data.get("npc_id", "")), str(data.get("child_name", "")))


@app.route("/api/world/legacy/continue", methods=["POST"])
def world_legacy_continue() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("continue_world_as_heir", str(data.get("heir_id", "")))


@app.route("/api/world/legacy/reincarnate", methods=["POST"])
def world_legacy_reincarnate() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call(
        "reincarnate_world_life",
        str(data.get("name", "Reborn Shinobi")),
        str(data.get("village_id", "")),
        str(data.get("clan_id", "")),
        str(data.get("nature_id", "")),
    )


@app.route("/api/world/career/apply", methods=["POST"])
def world_career_apply() -> Any:
    data = request.get_json(silent=True) or {}
    return _world_call("apply_for_world_job", str(data.get("job_id", "")))


@app.route("/api/world/career/work", methods=["POST"])
def world_career_work() -> Any:
    return _world_call("work_world_job")


@app.route("/api/world/save", methods=["POST"])
def world_save() -> Any:
    return _world_call("save_game")


@app.route("/api/world/llm/test", methods=["POST"])
def world_llm_test() -> Any:
    data = request.get_json(silent=True) or {}
    settings = load_llm_settings()
    base_url = str(data.get("base_url", settings.get("base_url", "http://127.0.0.1:1234"))).strip()
    model = str(data.get("model", settings.get("model", ""))).strip()
    connected, message = check_llm_connection(base_url, model)
    return jsonify({"success": connected, "message": message, "base_url": base_url, "model": model}), (200 if connected else 502)


@app.route("/api/new_game", methods=["POST"])
def new_game() -> Any:
    """Start a new game."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        name = data.get("name", "").strip()
        origin_id = data.get("origin", "")
        era = data.get("era", "modern")
        age = data.get("age", None)

        if not name:
            return jsonify({"error": "Name is required"}), 400

        engine = get_engine()
        with _game_lock:
            state = engine.new_game(name, origin_id)

            # Apply era and age overrides (matching the PySide6 app's behavior)
            if era and era != "modern":
                try:
                    from character_creation import build_character_template
                    template = build_character_template(name=name, era=era, age=age)
                    tpl_player = template["player"]
                    player = engine.state["player"]
                    player["era"] = tpl_player.get("era", era)
                    player["ui_stats"] = tpl_player.get("ui_stats", {})
                    if age is not None:
                        player["age"] = age
                    # Update world era
                    engine.state.setdefault("world", {})["era"] = normalize_era(era)
                except Exception as e:
                    app.logger.warning(f"Failed to apply era/age overrides: {e}")

            # Apply start year if provided
            start_year = data.get("start_year", 1)
            try:
                engine.state["year"] = int(start_year)
            except (TypeError, ValueError):
                pass

            try:
                engine._save()
            except Exception:
                pass

        return jsonify({
            "success": True,
            "state": public_state(state),
            "message": f"New game started: {name}"
        })
    except GameRuleError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to start new game: {str(e)}"}), 500


@app.route("/api/load_game", methods=["POST"])
def load_game() -> Any:
    """Load a saved game."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        folder = data.get("folder")
        engine = get_engine()

        with _game_lock:
            if folder:
                requested = Path(str(folder))
                base = GAMES_DIR.resolve()
                game_folder = requested.resolve() if requested.is_absolute() else (GAMES_DIR / requested.name).resolve()
                if game_folder.parent != base or not game_folder.is_dir():
                    raise GameRuleError("That save folder is not available.")
                state = engine.load_game(game_folder=game_folder)
            else:
                state = engine.load_game()

        return jsonify({
            "success": True,
            "state": public_state(state),
            "message": "Game loaded successfully"
        })
    except GameRuleError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to load game: {str(e)}"}), 500


@app.route("/api/list_games", methods=["GET"])
def list_saved_games() -> Any:
    """List all saved game folders with metadata."""
    try:
        games = list_games()
        return jsonify({
            "success": True,
            "games": games,
            "count": len(games)
        })
    except Exception as e:
        return jsonify({"error": f"Failed to list games: {str(e)}"}), 500


@app.route("/api/delete_game", methods=["POST"])
def delete_game() -> Any:
    """Delete a saved game folder."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        folder = data.get("folder", "").strip()
        if not folder:
            return jsonify({"error": "Folder name is required"}), 400

        result = delete_game_folder(folder)
        if result:
            return jsonify({"success": True, "message": f"Deleted game: {folder}"})
        else:
            return jsonify({"error": f"Could not delete game: {folder}"}), 404
    except Exception as e:
        return jsonify({"error": f"Failed to delete game: {str(e)}"}), 500


@app.route("/api/travel", methods=["POST"])
def travel() -> Any:
    """Travel to a location."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        location = data.get("location", "").strip()
        engine = get_engine()

        if not location:
            return jsonify({"error": "Location is required"}), 400

        with _game_lock:
            state = engine.travel(location)

        return jsonify({
            "success": True,
            "state": public_state(state),
            "message": f"Traveled to {location}"
        })
    except GameRuleError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to travel: {str(e)}"}), 500


@app.route("/api/interact", methods=["POST"])
def interact() -> Any:
    """Interact with an NPC."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        npc_id = data.get("npc_id", "").strip()
        action = data.get("action", "").strip()

        engine = get_engine()

        if not npc_id or not action:
            return jsonify({"error": "npc_id and action are required"}), 400

        with _game_lock:
            state = engine.interact(npc_id, action)

        return jsonify({
            "success": True,
            "state": public_state(state),
            "message": f"Interacted with {npc_id}: {action}"
        })
    except GameRuleError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to interact: {str(e)}"}), 500


@app.route("/api/choose", methods=["POST"])
def choose() -> Any:
    """Make a choice in a main seasonal event."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        choice_id = data.get("choice_id", "").strip()
        engine = get_engine()

        if not choice_id:
            return jsonify({"error": "choice_id is required"}), 400

        with _game_lock:
            state = engine.choose_main(choice_id)

        return jsonify({
            "success": True,
            "state": public_state(state),
            "message": "Choice made successfully"
        })
    except GameRuleError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to make choice: {str(e)}"}), 500


@app.route("/api/choose_random", methods=["POST"])
def choose_random() -> Any:
    """Make a choice in a random event."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        choice_id = data.get("choice_id", "").strip()
        engine = get_engine()

        if not choice_id:
            return jsonify({"error": "choice_id is required"}), 400

        with _game_lock:
            state = engine.choose_random(choice_id)

        return jsonify({
            "success": True,
            "state": public_state(state),
            "message": "Random event choice resolved"
        })
    except GameRuleError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to resolve random choice: {str(e)}"}), 500


@app.route("/api/resolve_encounter", methods=["POST"])
def resolve_encounter() -> Any:
    """Resolve an encounter (school decision, teen decision, etc.)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        choice_id = data.get("choice_id", "").strip()
        engine = get_engine()

        if not choice_id:
            return jsonify({"error": "choice_id is required"}), 400

        with _game_lock:
            state = engine.resolve_encounter(choice_id)

        return jsonify({
            "success": True,
            "state": public_state(state),
            "message": "Encounter resolved"
        })
    except GameRuleError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to resolve encounter: {str(e)}"}), 500


@app.route("/api/public_state", methods=["GET"])
def public_state_endpoint() -> Any:
    """Get current game state."""
    engine = get_engine()
    try:
        with _game_lock:
            state = engine.public_state()
    except GameRuleError:
        # A fresh launch has no active life yet; let the client show creation UI.
        state = None
    return jsonify({
        "success": True,
        "state": public_state(state) if state is not None else None
    })


@app.route("/api/save_game", methods=["POST"])
def save_game() -> Any:
    """Save the current game."""
    try:
        engine = get_engine()
        with _game_lock:
            engine._save()

        # Read the save file
        save_file = engine.save_file
        if save_file.exists():
            data = json.loads(save_file.read_text(encoding="utf-8"))
            return jsonify({
                "success": True,
                "save_file": os.path.basename(str(save_file)),
                "message": "Game saved successfully"
            })
        else:
            return jsonify({
                "success": True,
                "message": "Game saved (no file to read back)"
            })
    except Exception as e:
        return jsonify({"error": f"Failed to save game: {str(e)}"}), 500


@app.route("/api/get_origins", methods=["GET"])
def get_origins() -> Any:
    """Get available origins."""
    origins = []
    for origin in ORIGINS:
        origins.append({
            "id": origin["id"],
            "tag": origin.get("tag", ""),
            "name": origin.get("name", ""),
            "description": origin.get("description", ""),
            "effects": origin.get("effects", {})
        })
    return jsonify({"success": True, "origins": origins})


@app.route("/api/get_menu_slots", methods=["GET"])
def get_menu_slots_endpoint() -> Any:
    """Get menu slots for current era."""
    engine = get_engine()
    with _game_lock:
        era = engine.state.get("player", {}).get("era", "modern") if engine.state else "modern"
    slots = get_menu_slots(era)
    return jsonify({
        "success": True,
        "slots": slots
    })


@app.route("/api/get_dashboard_profile", methods=["GET"])
def get_dashboard_profile_endpoint() -> Any:
    """Get era-specific dashboard labels and profile fields."""
    engine = get_engine()
    with _game_lock:
        era = engine.state.get("player", {}).get("era", "modern") if engine.state else "modern"
    profile = get_dashboard_profile(era)
    return jsonify({
        "success": True,
        "profile": profile,
        "era": era
    })


@app.route("/api/get_llm_settings", methods=["GET"])
def get_llm_settings() -> Any:
    """Get LLM settings."""
    settings = load_llm_settings()
    return jsonify({
        "success": True,
        "settings": settings
    })


@app.route("/api/save_llm_settings", methods=["POST"])
def save_llm_settings_endpoint() -> Any:
    """Save LLM settings."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        settings = load_llm_settings()
        settings.update({
            "base_url": data.get("base_url", settings.get("base_url", "http://127.0.0.1:1234")),
            "model": data.get("model", settings.get("model", "local-model")),
            "enabled": data.get("enabled", settings.get("enabled", True)),
        })
        save_llm_settings(settings)
        return jsonify({
            "success": True,
            "message": "LLM settings saved"
        })
    except Exception as e:
        return jsonify({"error": f"Failed to save LLM settings: {str(e)}"}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  SERVER ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_engine()
    print(f"[Riverton API] Starting Flask server on {HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
