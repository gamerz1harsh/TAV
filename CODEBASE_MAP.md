# Riverton Codebase Map

This document provides a compact map of the codebase for limited context AI models, detailing module structure, dependencies, and architectural responsibilities.

## System Overview (Dependency Flow)

The application follows a strict separation of concerns:
1.  **Core Simulation/Game Logic (`game_engine`, `character_creation`):** Pure Python logic, independent of GUI frameworks ($\text{PySide6}$) or UI components (`desktop/*`). This layer manages state, rules, and history.
2.  **UI/Presentation Layer (`main.py`, `desktop/*`):** Responsible for rendering the application and handling user input via PySide6 signals and slots. It *calls* simulation methods but should not contain core logic itself.
3.  **Data/Utility Layer:** Handles persistent storage, configuration, logging, and external services (LLM).

**Core Architecture Rule:** `game_engine` and all simulation code must **NOT** depend on PySide6 or any UI component in `desktop/*`.

## Module Breakdown

### 📂 Core Simulation & Game Logic

#### `game_engine.py`
*   **Purpose:** Manages the core game state, progression (time, resources), event processing, and rule enforcement. It is the single source of truth for the simulation state.
*   **Important Classes/Functions:**
    *   `GameEngine`: Main class managing the entire game lifecycle.
        *   `__init__()`: Sets up initial state and log callbacks.
        *   `new_game(name, origin_id)`: Initializes a new game state based on character creation data. Called by `main.py`.
        *   `load_game(game_folder)`: Loads state from persistent storage. Called by `main.py`.
    *   **Dependencies:** Depends on `LOCATIONS`, `ORIGINS`, and potentially external configuration/data files (`SAVE_FILE`).
    *   **Calls/Used By:** `main.py` (via `RivertonWindow._start_new_game`, `_continue_game`), `event_director.py`.
*   **System:** Simulation, Storage

#### `character_creation.py`
*   **Purpose:** Handles the deterministic process of generating a character's base template data from user input parameters (Name, Era, Age).
*   **Important Functions/Methods:**
    *   `enumerate_eras()`: Lists all recognized eras. Used by `main.py`.
    *   `build_character_template(name, era, age)`: Generates the initial structured dictionary containing player stats and attributes. Called by `main.py`.
    *   `validate_era(era)`: Checks if a provided string is a valid game era.
*   **Dependencies:** None (Pure Python logic).
*   **Calls/Used By:** `main.py` (via `RivertonWindow._build_creation_page`, `_apply_character_template`).
*   **System:** Simulation, Character

#### `event_director.py`
*   **Purpose:** Selects the most thematically and logically interesting event from a pool of candidates based on current game context (player stats, location, flags). It is the decision-making layer for story progression.
*   **Important Functions/Methods:**
    *   `score_event(event, context, recent_ids)`: Calculates a weighted score for an event using complex rules (relevance, tension, novelty, etc.). Takes `context` dictionary as input.
    *   `select_event(candidates, context, recent_ids)`: Orchestrates the scoring process and returns the single best candidate. Logs all decisions to `director_log.jsonl`.
*   **Dependencies:** Depends on global data structures like `LOCATIONS`, `ORIGINS`.
*   **Calls/Used By:** Expected to be called by a core game loop function within `game_engine.py` (not explicitly visible in context).
*   **System:** Event, Simulation

### 📂 UI & Presentation Layer

#### `main.py`
*   **Purpose:** The main application entry point (`RivertonWindow`). It orchestrates the entire UI flow: setting up views, handling state transitions between pages, and connecting user input to core logic calls.
*   **Important Classes/Functions:**
    *   `RivertonWindow`: Main window controller.
        *   `__init__()`: Initializes components, sets up dev console, calls `_build_menu_bar()` and `_build_pages()`.
        *   `_build_pages()`: Sets up the main `QStackedWidget` containing all screens.
        *   `_build_setup_page()`: *[Deprecated/Replaced]* Used to build the initial setup view (replaces logic in `StartScreen`).
        *   `_build_game_page()`: Builds the main gameplay interface layout, including age circle, stats, and chronicle.
        *   `_start_new_game()` / `_continue_game()`: Coordinates calling `GameEngine` methods and updating UI state upon success.
    *   **Dependencies:** Depends on almost all other modules (`game_engine`, `character_creation`, `dev_console`, etc.).
    *   **Calls/Used By:** N/A (Entry Point).
*   **System:** UI, Development

#### `desktop/screens/start_screen.py` (New Component)
*   **Purpose:** Encapsulates the initial setup screen UI and user interaction logic, emitting signals instead of calling internal window methods. Achieves component decoupling.
*   **Important Classes/Functions:**
    *   `StartScreen(QWidget)`: The widget class for the startup page.
        *   Defines and emits `new_game_requested.emit()` and `continue_requested.emit()` signals upon user interaction (e.g., button clicks).
*   **Dependencies:** Depends on UI widgets (`PySide6`).
*   **Calls/Used By:** `main.py` (connects signals to window handlers).
*   **System:** UI

### 📂 Utility & Data Storage

#### `dev_console.py`
*   **Purpose:** Provides a dedicated, persistent log display area for debugging and system messages during runtime.
*   **Important Classes/Functions:**
    *   `DevConsole`: Manages logging output in the main window's dockable area.
    *   `info()`, `log()`: Methods to append formatted, colored text to the internal log widget.
*   **Dependencies:** Depends on PySide6 for UI elements (`QTextEdit`).
*   **Calls/Used By:** `main.py`.
*   **System:** Development

#### `game_config.py` / `data/*`
*   **Purpose:** Holds global, read-only application constants (e.g., `LOCATIONS`, `ORIGINS`) and manages file system interactions for game saving/loading (`GAMES_DIR`).
*   **Important Functions:**
    *   `list_games()`: Reads save metadata from the directory structure.
*   **Dependencies:** File System I/O.
*   **Calls/Used By:** `main.py`.
*   **System:** Storage, Configuration

### 📂 Development & Testing

#### `requirements.txt`, `tests/*`
*   **Purpose:** Defines dependencies and contains unit tests for validating core logic components.
*   **System:** Tests, Development

## Refactor Status

- **`APP_STYLE`**: Has been successfully moved from `main.py` to a dedicated file: `desktop/theme.py`.
- **StartScreen Extraction**: The entire initial view layer has been extracted into the signal-driven component `desktop/screens/start_screen.py`. This was the immediate goal of this refactoring phase.
- **Next Planned UI Task:** Finalizing the wiring up of all signals in `main.py` to ensure every user interaction on the new `StartScreen` correctly triggers the corresponding state change or logic path within `RivertonWindow`.

## Architecture Inconsistencies Noticed

1.  **Direct Dependency (High Risk):** The current structure relies heavily on `game_engine.py` being called by `main.py`, which is UI-dependent. Any future changes to the simulation flow *must* be tested against the assumption that the game state can be initialized and progressed without direct calls from `main.py`.
2.  **Event Director Context:** `event_director.py` relies on a very rich `context: dict[str, Any]` dictionary which must contain player stats, location, flags, NPC details, etc. This context object needs to be consistently generated by the module responsible for state advancement (likely within `game_engine.py`).
3.  **Test Coverage Gap:** The unit tests (`tests/*`) do not appear to adequately mock or simulate complex cross-module interactions (e.g., simulating a full turn cycle: Event Director $\rightarrow$ Game Engine $\rightarrow$ State Update). This is the highest risk area for future bugs.