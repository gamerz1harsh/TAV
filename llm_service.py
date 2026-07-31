"""Simple local LLM integration for Riverton.

This module keeps the game rules authoritative while allowing an optional
LLM-backed narrative layer to propose dynamic year-advance options.
It targets LM Studio's OpenAI-compatible local endpoint by default.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).parent
SETTINGS_FILE = ROOT / "data" / "llm_settings.json"
DEFAULT_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
DEFAULT_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")
DEFAULT_TIMEOUT = 30


def _candidate_endpoints(base_url: str) -> list[str]:
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    bases = [base]
    if base.endswith("/v1"):
        bases.append(base[:-3])
    else:
        bases.append(f"{base}/v1")

    seen: set[str] = set()
    candidates: list[str] = []
    preferred_suffixes = ["/chat/completions", "/chat/completions"]
    for prefix in bases:
        for suffix in preferred_suffixes:
            candidate = f"{prefix}{suffix}"
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    return candidates


class LLMServiceError(RuntimeError):
    """Raised when the local model cannot be reached or returns invalid data."""


def load_llm_settings() -> dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {"base_url": DEFAULT_BASE_URL, "model": DEFAULT_MODEL, "enabled": True}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"base_url": DEFAULT_BASE_URL, "model": DEFAULT_MODEL, "enabled": True}


def save_llm_settings(settings: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _strip_json_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        char = text[i]
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            i += 1
            continue

        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue

        if char == "/" and i + 1 < len(text) and text[i + 1] == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue

        result.append(char)
        i += 1

    return "".join(result)


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_llm_response(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    marker_prefixes = ["<channel|>", "<|channel|>", "<think>", "</think>"]
    for prefix in marker_prefixes:
        if prefix in text:
            text = text.split(prefix, 1)[1]

    if text.startswith("json"):
        text = text[4:].strip()

    cleaned = _strip_json_comments(text)
    candidate = _extract_json_object(cleaned)
    if candidate is not None:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(cleaned)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise LLMServiceError("LLM returned no usable JSON payload") from None


def _extract_llm_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content") or message.get("reasoning_content")
                if isinstance(content, str) and content.strip():
                    return content
            text = first_choice.get("text")
            if isinstance(text, str) and text.strip():
                return text
            reasoning = first_choice.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning
    content = data.get("content")
    if isinstance(content, str) and content.strip():
        return content
    text = data.get("text")
    if isinstance(text, str) and text.strip():
        return text
    return None


def _build_llm_request(endpoint: str, model: str, messages: list[dict[str, str]] | None = None, prompt: str | None = None, temperature: float = 0.7, max_tokens: int = 220) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "temperature": temperature, "max_tokens": max_tokens}
    endpoint_low = endpoint.lower()
    if "/chat" in endpoint_low or "/api/v1/chat" in endpoint_low:
        payload["messages"] = messages or []
        payload["stream"] = False
    else:
        payload["prompt"] = prompt or ""
        payload["stream"] = False
    return payload


def build_fallback_options(state: dict[str, Any]) -> list[dict[str, Any]]:
    player = state.get("player", {})
    stats = player.get("stats", {})
    location = player.get("location", "apartment")
    flags = state.get("flags", {})
    npcs = state.get("npcs", [])
    priya_trust = next((npc.get("trust", 0) for npc in npcs if npc.get("id") == "priya"), 0)
    sam_trust = next((npc.get("trust", 0) for npc in npcs if npc.get("id") == "sam"), 0)

    options = [
        {
            "id": "cafe_focus",
            "label": "Lean into the cafe",
            "description": "Build dependable work, steady money, and stronger ties with Priya.",
            "effects": {"money": 1, "energy": -1, "trust": {"priya": 1}, "flags": {"cafe_focus": True}},
        },
        {
            "id": "community_focus",
            "label": "Double down on the neighborhood",
            "description": "Spend more time with Sam and grow your public reputation.",
            "effects": {"reputation": 1, "energy": -1, "trust": {"sam": 1}, "flags": {"community_focus": True}},
        },
        {
            "id": "study_focus",
            "label": "Prioritize skill and study",
            "description": "Invest in knowledge and long-term opportunity.",
            "effects": {"skill": 1, "energy": -1, "flags": {"study_focus": True}},
        },
    ]

    if location == "cafe" or flags.get("cafe_shift"):
        options.insert(0, {
            "id": "cafe_shift",
            "label": "Take another cafe shift",
            "description": "If you have been helping at the cafe, this keeps the rhythm going.",
            "effects": {"money": 2, "energy": -1, "trust": {"priya": 1}},
        })
    if stats.get("money", 0) <= 0 or priya_trust >= 2:
        options.append({
            "id": "stabilize_money",
            "label": "Stabilize your finances",
            "description": "Focus on steady income and keeping your footing.",
            "effects": {"money": 1, "energy": -1},
        })
    if stats.get("reputation", 0) >= 1 or sam_trust >= 1:
        options.append({
            "id": "public_leadership",
            "label": "Take a public leadership step",
            "description": "Use your growing reputation to become more visible.",
            "effects": {"reputation": 1, "trust": {"sam": 1}},
        })
    return options[:4]


def should_use_async_llm() -> bool:
    return os.getenv("RIVERTON_USE_ASYNC_LLM", "1") == "1"


def build_async_payload(state: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    return {
        "model": model or os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": "You help propose a few meaningful seasonal directions for a life-sim game."},
            {"role": "user", "content": build_prompt(state)},
        ],
        "temperature": 0.7,
        "max_tokens": 220,
        "stream": False,
        "mode": "async",
    }


def build_prompt(state: dict[str, Any]) -> str:
    player = state.get("player", {})
    stats = player.get("stats", {})
    location = player.get("location", "apartment")
    flags = state.get("flags", {})
    npc_summary = []
    for npc in state.get("npcs", []):
        npc_summary.append(f"{npc.get('id')}: trust={npc.get('trust',0)}, affinity={npc.get('affinity',0)}")
    
    # Retrieve recent memories for context
    memory_context = ""
    try:
        from memory_store import retrieve_memories
        recent_memories = retrieve_memories(max_results=5, boost_recent=True)
        if recent_memories:
            memory_lines = [mem.get("text", "") for mem in recent_memories]
            memory_context = "Recent memories: " + " | ".join(memory_lines) + ". "
    except Exception:
        pass
    
    return (
        "Return ONLY valid JSON. "
        "Do not include markdown, code fences, commentary, reasoning, or prose. "
        "Output a single JSON object with one key named 'options'. "
        "The value of 'options' must be an array of 2 to 4 objects. "
        "Each option object must contain only these keys: id, label, description, effects. "
        "The effects object must be a JSON object with numeric values and simple strings/booleans. "
        f"Current location: {location}. "
        f"Stats: energy={stats.get('energy',0)}, money={stats.get('money',0)}, skill={stats.get('skill',0)}, reputation={stats.get('reputation',0)}. "
        f"Flags: {json.dumps(flags)}. "
        f"NPC state: {', '.join(npc_summary)}. "
        f"{memory_context}"
        "Keep the choices grounded in the current state and avoid impossible actions."
    )


def get_dynamic_year_options(state: dict[str, Any], base_url: str | None = None, model: str | None = None, enabled: bool | None = None) -> list[dict[str, Any]]:
    settings = load_llm_settings()
    if enabled is None:
        enabled = settings.get("enabled", True)
    if not enabled or os.getenv("RIVERTON_USE_LLM", "1") != "1":
        return build_fallback_options(state)

    payload = build_async_payload(state, model or settings.get("model") or os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL))
    if should_use_async_llm():
        result_holder: dict[str, Any] = {"value": None}

        def worker() -> None:
            endpoint_base = base_url or settings.get("base_url") or os.getenv("LM_STUDIO_BASE_URL", DEFAULT_BASE_URL)
            last_error: Exception | None = None
            for endpoint in _candidate_endpoints(endpoint_base):
                try:
                    request_payload = _build_llm_request(
                        endpoint,
                        model or settings.get("model") or os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL),
                        messages=[
                            {"role": "system", "content": "You help propose a few meaningful seasonal directions for a life-sim game."},
                            {"role": "user", "content": build_prompt(state)},
                        ],
                        prompt=build_prompt(state),
                        temperature=0.7,
                        max_tokens=220,
                    )
                    response = requests.post(endpoint, json=request_payload, timeout=DEFAULT_TIMEOUT)
                    if response.status_code >= 400:
                        last_error = RuntimeError(f"endpoint {endpoint} returned {response.status_code}")
                        continue
                    response.raise_for_status()
                    data = response.json()
                    content: str | None = None
                    if isinstance(data, dict):
                        content = _extract_llm_text(data)
                    if not isinstance(content, str):
                        raise LLMServiceError("LLM returned no usable text content")
                except (KeyError, IndexError, TypeError, requests.RequestException, LLMServiceError) as exc:
                    last_error = exc
                    continue
                try:
                    parsed = parse_llm_response(content)
                except Exception:
                    result_holder["value"] = build_fallback_options(state)
                    return

                options = parsed.get("options", [])
                if isinstance(options, list) and options:
                    result_holder["value"] = options
                    return
            result_holder["value"] = build_fallback_options(state)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        # Wait for the thread to complete with a timeout
        thread.join(timeout=DEFAULT_TIMEOUT + 5)
        # Use the thread result if available, otherwise fallback
        if result_holder["value"] is not None:
            return result_holder["value"]
        return build_fallback_options(state)

    endpoint_base = base_url or settings.get("base_url") or os.getenv("LM_STUDIO_BASE_URL", DEFAULT_BASE_URL)
    last_error: Exception | None = None
    for endpoint in _candidate_endpoints(endpoint_base):
        try:
            request_payload = _build_llm_request(
                endpoint,
                model or settings.get("model") or os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL),
                messages=[
                    {"role": "system", "content": "You help propose a few meaningful seasonal directions for a life-sim game."},
                    {"role": "user", "content": build_prompt(state)},
                ],
                prompt=build_prompt(state),
                temperature=0.7,
                max_tokens=220,
            )
            response = requests.post(endpoint, json=request_payload, timeout=DEFAULT_TIMEOUT)
            if response.status_code >= 400:
                last_error = RuntimeError(f"endpoint {endpoint} returned {response.status_code}")
                continue
            response.raise_for_status()
            data = response.json()
            content: str | None = None
            if isinstance(data, dict):
                content = _extract_llm_text(data)
            if not isinstance(content, str):
                raise LLMServiceError("LLM returned no usable text content")
        except (KeyError, IndexError, TypeError, requests.RequestException, LLMServiceError) as exc:
            last_error = exc
            continue
        try:
            parsed = parse_llm_response(content)
        except Exception:
            return build_fallback_options(state)

        options = parsed.get("options", [])
        if isinstance(options, list) and options:
            return options

    return build_fallback_options(state)


def generate_starting_scenario(template: dict[str, Any], base_url: str | None = None, model: str | None = None, enabled: bool | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Ask the LLM to generate a starting scenario, NPCs and a small map.

    Returns a dict with keys: `scenario` (text), `map` (dict), `npcs` (list).
    Falls back to a deterministic minimal scenario when LLM is unavailable.
    """
    settings = load_llm_settings()
    if enabled is None:
        enabled = settings.get("enabled", True)
    if not enabled or os.getenv("RIVERTON_USE_LLM", "1") != "1":
        return {
            "scenario": "A modest day in Riverton: the cafe and college hum with possibility.",
            "map": {"center": "Juniper Cafe", "locations": {"apartment": "Your cozy apartment", "cafe": "Juniper Cafe - a warm local spot", "college": "Riverton Community College"}},
            "npcs": [],
        }

    player = template.get("player", {})
    player_name = player.get("name", "Player")
    player_age = player.get("age", 25)
    player_era = player.get("era", "modern")
    origin_id = template.get("origin_id", "new_arrival")

    # Build age-appropriate context
    if player_age is not None and player_age < 10:
        age_context = (
            f"The player is {player_age} years old, a young child. "
            "The scenario must be age-appropriate: set in a safe, familiar environment like home, "
            "a kindergarten, a neighborhood park, or a family-friendly community space. "
            "NPCs should be family members, caregivers, teachers, or friendly neighbors. "
            "No dangerous situations, forests, or adult responsibilities."
        )
    elif player_age is not None and player_age < 16:
        age_context = (
            f"The player is {player_age} years old, a teenager. "
            "The scenario should be set in a school, neighborhood, or local hangout spots. "
            "NPCs can include friends, teachers, family, and local shopkeepers. "
            "Keep stakes appropriate for a young person's world."
        )
    else:
        age_context = (
            f"The player is {player_age} years old, an adult. "
            "The scenario can include work, community, relationships, and adult responsibilities."
        )

    prompt = (
        "Return ONLY valid JSON. "
        "Do not include markdown, code fences, commentary, reasoning, or prose. "
        "Return a single JSON object with exactly these keys: 'scenario', 'map', and 'npcs'. "
        "'scenario' must be a short 2-3 sentence narrative introduction. "
        "'map' must be an object with a 'center' (string, the main hub location name) and 'locations' "
        "(an object where keys are location IDs and values are short descriptions). "
        "Include 3-5 locations. One should be the player's home. "
        "'npcs' must be an array of 2-4 NPC objects. "
        "Each NPC must include: id (string, unique), name (string), role (string), "
        "location (string, one of the map location IDs), affinity (integer -1 to 3), "
        "trust (integer 0 to 3), and description (string, 1-2 sentences). "
        f"Player name: {player_name}. "
        f"Player age: {player_age}. Era: {player_era}. "
        f"{age_context} "
        "Ensure the scenario, locations, and NPCs are all thematically consistent with the age, era, and setting. "
        "The scenario should feel like a natural starting point for a life simulation game."
    )

    # Attempt to generate using structured messages (Chat Completion API - e.g., /v1/chat/completions)
    messages = [
        {"role": "system", "content": "You generate small grounded starting scenarios for a life-sim game. You create age-appropriate, coherent settings with memorable NPCs and locations."},
        {"role": "user", "content": prompt},
    ]

    endpoint_base = base_url or settings.get("base_url") or os.getenv("LM_STUDIO_BASE_URL", DEFAULT_BASE_URL)
    last_error: Exception | None = None
    for endpoint in _candidate_endpoints(endpoint_base):
        try:
            request_payload = _build_llm_request(
                endpoint,
                model or settings.get("model") or os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL),
                messages=messages,
                prompt=prompt,
                temperature=0.8,
                max_tokens=800,
            )
            response = requests.post(endpoint, json=request_payload, timeout=timeout)
            if response.status_code >= 400:
                last_error = RuntimeError(f"endpoint {endpoint} returned {response.status_code}")
                continue
            response.raise_for_status()
            data = response.json()
            content: str | None = None
            if isinstance(data, dict):
                content = _extract_llm_text(data)
            if not isinstance(content, str):
                raise LLMServiceError("LLM returned no usable text content")
        except (KeyError, IndexError, TypeError, requests.RequestException, LLMServiceError) as exc:
            last_error = exc
            continue
        try:
            parsed = parse_llm_response(content)
        except Exception:
            continue

        scenario = parsed.get("scenario")
        map_obj = parsed.get("map")
        npcs = parsed.get("npcs")
        if isinstance(scenario, str) and isinstance(map_obj, dict) and isinstance(npcs, list):
            # Validate map structure
            if isinstance(map_obj.get("locations"), dict):
                return {"scenario": scenario, "map": map_obj, "npcs": npcs}
            # If locations is a list, convert to dict with descriptions
            elif isinstance(map_obj.get("locations"), list):
                locs = {}
                for loc in map_obj["locations"]:
                    if isinstance(loc, str):
                        locs[loc] = loc.replace("_", " ").title()
                    elif isinstance(loc, dict) and "id" in loc:
                        locs[loc["id"]] = loc.get("description", loc["id"])
                map_obj["locations"] = locs
                return {"scenario": scenario, "map": map_obj, "npcs": npcs}

    # fallback
    return {
        "scenario": "A modest day in Riverton: the cafe and college hum with possibility.",
        "map": {"center": "Juniper Cafe", "locations": {"apartment": "Your cozy apartment", "cafe": "Juniper Cafe - a warm local spot", "college": "Riverton Community College"}},
        "npcs": [],
    }


# ----- Narration Layer -----


def _call_llm_text(
    system_prompt: str,
    user_prompt: str,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 150,
    timeout: int = DEFAULT_TIMEOUT,
) -> str | None:
    """Internal helper: call the LLM and return the raw text response, or None on failure."""
    settings = load_llm_settings()
    if not settings.get("enabled", True):
        return None

    endpoint_base = base_url or settings.get("base_url") or os.getenv("LM_STUDIO_BASE_URL", DEFAULT_BASE_URL)
    model_name = model or settings.get("model") or os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for endpoint in _candidate_endpoints(endpoint_base):
        try:
            payload = _build_llm_request(
                endpoint,
                model_name,
                messages=messages,
                prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response = requests.post(endpoint, json=payload, timeout=timeout)
            if response.status_code >= 400:
                continue
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                content = _extract_llm_text(data)
                if isinstance(content, str) and content.strip():
                    return content.strip()
        except (KeyError, IndexError, TypeError, requests.RequestException, LLMServiceError):
            continue
    return None


def generate_event_description(
    event_title: str,
    event_text: str,
    player_name: str,
    location: str,
    npc_name: str | None = None,
) -> str:
    """Generate a short narrated description of an event.

    Falls back to the event text itself when the LLM is unavailable.
    """
    llm_text = _call_llm_text(
        "You narrate short event descriptions for a life-sim game. Keep it to 2-3 sentences.",
        (
            f"Describe this event from {player_name}'s perspective at {location}."
            f"Event: {event_title} - {event_text}"
            + (f" NPC involved: {npc_name}." if npc_name else "")
        ),
        max_tokens=120,
    )
    if llm_text:
        return llm_text
    # Fallback: return the base event text
    return event_text


def generate_npc_dialogue(
    npc_name: str,
    npc_role: str,
    context: str,
    relationship: str = "neutral",
) -> str:
    """Generate a short line of NPC dialogue based on context and relationship.

    Args:
        npc_name: The NPC's name.
        npc_role: The NPC's role (e.g., "cafe manager").
        context: The situation or event context.
        relationship: "neutral", "friendly", "cold", "trusting".

    Returns:
        A short dialogue line.
    """
    tone_map = {
        "friendly": "warm and encouraging",
        "cold": "distant and short",
        "trusting": "open and personal",
        "neutral": "casual and neutral",
    }
    tone = tone_map.get(relationship, "casual and neutral")

    llm_text = _call_llm_text(
        f"You are {npc_name}, a {npc_role} in a life-sim game. Respond in character with a {tone} tone. Keep it to one short sentence.",
        f"Context: {context}",
        max_tokens=80,
    )
    if llm_text:
        return llm_text

    # Fallback dialogue lines by relationship
    fallbacks = {
        "friendly": [
            f"{npc_name} smiles warmly. \"Good to see you. Really.\"",
            f"{npc_name} nods. \"You're doing alright, you know.\"",
            f"{npc_name} says, \"Glad you stopped by.\"",
        ],
        "cold": [
            f"{npc_name} gives a short nod. \"Busy.\"",
            f"{npc_name} barely looks up. \"What do you need?\"",
            f"{npc_name} shrugs. \"Not much to say.\"",
        ],
        "trusting": [
            f"{npc_name} leans in. \"I've been thinking about what you said.\"",
            f"{npc_name} speaks quietly. \"I trust your judgment on this.\"",
            f"{npc_name} meets your eyes. \"Thank you for being here.\"",
        ],
        "neutral": [
            f"{npc_name} says, \"How's your day going?\"",
            f"{npc_name} glances over. \"Interesting times.\"",
            f"{npc_name} offers a small smile. \"Hey.\"",
        ],
    }
    import random
    return random.choice(fallbacks.get(relationship, fallbacks["neutral"]))


def generate_season_narration(
    season: str,
    player_name: str,
    focus: str,
    stats_changes: list[str],
    npc_changes: list[str],
) -> str:
    """Generate a short seasonal narration paragraph.

    Falls back to a template-based summary when the LLM is unavailable.
    """
    changes_text = ", ".join(stats_changes) if stats_changes else "little change"
    npc_text = "; ".join(npc_changes[:3]) if npc_changes else "no major relationship shifts"

    llm_text = _call_llm_text(
        "You narrate season summaries for a life-sim game. Write 2-3 evocative sentences.",
        (
            f"{season} in Riverton. {player_name} focused on {focus}. "
            f"Stats: {changes_text}. Relationships: {npc_text}. "
            "Describe the season's mood and feel."
        ),
        max_tokens=130,
    )
    if llm_text:
        return llm_text

    # Fallback template
    template = f"{season} in Riverton. {player_name} focused on {focus.lower()}. "
    if stats_changes:
        template += f"Key shifts: {changes_text}. "
    if npc_changes:
        template += f"Relationship changes: {npc_text}. "
    template += "The season moved forward, and the streets of Riverton continue to hold their stories."
    return template


def generate_mood_reaction(
    mood: str,
    location: str,
    player_name: str,
    recent_event: str | None = None,
) -> str:
    """Generate a short mood-sensitive atmospheric description.

    Args:
        mood: One of "peaceful", "tense", "hopeful", "tired", "reflective".
        location: The current location.
        player_name: The player's name.
        recent_event: An optional recent event for context.

    Returns:
        A short atmospheric description.
    """
    context = f"Recent: {recent_event}." if recent_event else "An ordinary day."

    llm_text = _call_llm_text(
        f"Describe the atmosphere at {location} in a life-sim game. The mood is {mood}. Keep it to 1-2 sentences.",
        f"{player_name} is at {location}. {context} The mood is {mood}.",
        max_tokens=100,
    )
    if llm_text:
        return llm_text

    # Fallback mood descriptions
    mood_fallbacks = {
        "peaceful": f"The {location} feels calm. Sunlight filters through the windows, and for a moment, everything is still.",
        "tense": f"There's an edge in the air at the {location}. Conversations are quieter, and the usual warmth feels thinner.",
        "hopeful": f"Something in the air at the {location} feels lighter today. Possibility hums beneath the surface.",
        "tired": f"The {location} feels heavy. {player_name}'s energy is low, and even small sounds seem louder than they should.",
        "reflective": f"At the {location}, {player_name} finds a quiet corner. The day's events settle into something like perspective.",
    }
    return mood_fallbacks.get(mood, f"The {location} looks the way it always does, but today feels different.")

