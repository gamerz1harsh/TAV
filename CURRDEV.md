# Development Log

## Project goal
Riverton is a desktop-first life simulation game built in Python with a deterministic rules engine and an optional local LLM layer for dynamic seasonal choices.

## Current version status
The project is now in a playable desktop prototype phase with a rules engine, UI, local LLM support, and several gameplay systems layered on top.

## Features added

### Core gameplay
- Desktop launcher using PySide6
- New game flow with name and origin selection
- Seasonal progression with actions, travel, interactions, and main decisions
- Random event resolution
- End-of-year outcome resolution
- Local JSON save/load support

### UI and feedback systems
- Main dashboard with stats, location buttons, NPC cards, journal, and decision flow
- Season progress display
- Journal with memory filtering between recent and all memories
- Season summary panel after major choices
- Character sheet and relationship panel showing:
  - player stats
  - current location
  - NPC trust and affinity
  - current paths/opportunities
  - latest season summary

### Local LLM integration
- Optional integration with LM Studio-compatible local models
- OpenAI-compatible request support for local inference
- Settings menu for:
  - base URL
  - model name
  - enable/disable toggle
- Async/background request path so the UI remains responsive while the model is thinking

### Gameplay systems
- Lightweight season summary generation
- Memory filtering for journal readability
- Relationship/state-based story signal support for future narrative expansion

## Problems encountered and solved

### 1. PySide import issue
- Problem: QAction could not be imported from QtWidgets.
- Solution: Imported QAction from PySide6.QtGui, which is the correct module.

### 2. LM Studio endpoint mismatch
- Problem: The app initially targeted the wrong endpoint shape and the model server rejected the request.
- Solution: Added compatibility for common LM Studio and OpenAI-style paths such as /v1/chat/completions and /v1/completions.

### 3. UI freezing during LLM requests
- Problem: The game would appear to stall when asking the local model for options.
- Solution: Moved LLM calls onto a background thread so location changes and button actions remain responsive.

### 4. Missing dependency for HTTP requests
- Problem: The environment lacked the requests package needed for local model communication.
- Solution: Installed requests into the project virtual environment.

## Problems still open / not yet solved

### 1. LLM response quality is still basic
- The model can provide dynamic options, but the output is still simple and constrained by the prompt format.
- Next step: richer prompt design and structured response handling.

### 2. LLM latency is still variable
- Local inference can still be slow depending on hardware and model size.
- Next step: add a visible “thinking” state and better caching or throttling.

### 3. Narrative depth is still limited
- The game has systems for summaries and relationships, but NPC arcs and story progression are still fairly shallow.
- Next step: expand story triggers and milestone-based NPC progression.

### 4. Save/load polish is still basic
- The app saves locally, but there is no multi-slot save management yet.
- Next step: add save slots and autosave polish.

## Files in current development
- [game_engine.py](game_engine.py): core rules and state logic
- [main.py](main.py): desktop UI and screen rendering
- [llm_service.py](llm_service.py): local model integration and request handling
- [game_features.py](game_features.py): gameplay features such as season summaries, memory filtering, and character sheet data
- [tests/test_llm_service.py](tests/test_llm_service.py): LLM-related tests
- [tests/test_game_features.py](tests/test_game_features.py): feature tests
- [tests/test_character_sheet.py](tests/test_character_sheet.py): character sheet tests
- [tests/test_async_llm.py](tests/test_async_llm.py): async LLM behavior tests

## Next priority
Add richer NPC story arcs and milestone-based relationship progression so relationships feel like real storylines rather than numeric values.
