# Game Config System - Implementation TODO

## Goal
Make the game fully data-driven via JSON config files. Each game creates a per-game folder named `{player_name}_{date}` containing map, NPC, events, scenario, and save JSON files that the game loads.

## Steps

- [ ] 1. Create `data/game_config.json` - Global default game config (NPC templates, origins, locations, seasons, main events, random events, NPC arcs)
- [ ] 2. Create `game_config.py` - Config loader + per-game folder/data manager module
  - [ ] `load_game_config()` - Load & validate global config with fallback defaults
  - [ ] `get_npc_templates()`, `get_origins()`, `get_locations()`, `get_main_events()`, `get_random_events()`, `get_seasons()`, `get_npc_arcs()`
  - [ ] `create_game_folder(player_name)` - Creates `data/games/{name}_{timestamp}/`
  - [ ] `get_game_folder(player_name)` - Find folder by player name
  - [ ] `list_games()` - List all saved games
  - [ ] `write_game_json(folder, filename, data)` / `read_game_json(folder, filename)` - Per-game JSON I/O
  - [ ] `load_game_data(folder)` - Load all per-game JSON files (map, npcs, events, scenario)
- [ ] 3. Modify `game_engine.py`
  - [ ] Replace all hardcoded constants with `game_config` accessors
  - [ ] `new_game()` creates per-game folder, saves map/npcs/events from generated data
  - [ ] Save file moves into per-game folder
  - [ ] `load_game()` finds & reads from per-game folder
  - [ ] Helper `_game_folder()` to track current game folder
- [ ] 4. Modify `llm_service.py`
  - [ ] `generate_starting_scenario()` saves generated map/npcs/scenario to game folder as JSON files
  - [ ] New functions to load per-game generated JSON files
- [ ] 5. Modify `main.py`
  - [ ] Import ORIGINS, LOCATIONS from `game_config`
  - [ ] Update save/continue flow for per-game folders
  - [ ] Game selection dialog to pick from saved game folders
  - [ ] Pass game folder to GameEngine
- [ ] 6. Modify `npc_arcs.py`
  - [ ] Load NPC arc definitions from `game_config`
- [ ] 7. Modify `memory_store.py`
  - [ ] Per-game memories file (inside game folder)
- [ ] 8. Update `game_features.py` if needed for per-game data
- [ ] 9. Update tests for new config system
- [ ] 10. Verify game runs with JSON-driven data
