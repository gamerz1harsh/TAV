"""Event Queue System for Riverton V1.

Delayed and chained events. Events can be enqueued with a delay (in game
years or seasons) and will fire when the game advances past their trigger
point. This decouples event production from event handling.
"""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from pathlib import Path


class EventQueue:
    """A queue of delayed events that fire when the game advances."""

    def __init__(self) -> None:
        self.queue: deque[dict[str, Any]] = deque()

    def enqueue(
        self,
        event: dict[str, Any],
        *,
        delay_years: int = 0,
        delay_seasons: int = 0,
        trigger_age: int | None = None,
        trigger_flag: str | None = None,
        trigger_flag_value: bool = True,
    ) -> None:
        """Enqueue an event to fire later.

        Args:
            event: The event definition to fire.
            delay_years: Number of game years to wait.
            delay_seasons: Number of seasons to wait.
            trigger_age: Fire when the player reaches this age.
            trigger_flag: Fire when this flag is set.
            trigger_flag_value: The flag value to check for.
        """
        self.queue.append({
            "event": event,
            "delay_years": delay_years,
            "delay_seasons": delay_seasons,
            "trigger_age": trigger_age,
            "trigger_flag": trigger_flag,
            "trigger_flag_value": trigger_flag_value,
            "enqueued_at": time.time(),
            "fired": False,
        })

    def process(
        self,
        *,
        current_year: int,
        current_season_index: int,
        player_age: int,
        flags: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Process the queue and return events that are ready to fire.

        Args:
            current_year: The current game year.
            current_season_index: The current season index.
            player_age: The player's current age.
            flags: Current game flags.

        Returns:
            A list of event definitions that are ready to fire.
        """
        ready: list[dict[str, Any]] = []
        still_pending: deque[dict[str, Any]] = deque()

        for item in self.queue:
            if item.get("fired"):
                continue

            should_fire = False

            # Check trigger age
            trigger_age = item.get("trigger_age")
            if trigger_age is not None and player_age >= trigger_age:
                should_fire = True

            # Check trigger flag
            trigger_flag = item.get("trigger_flag")
            if trigger_flag is not None and flags.get(trigger_flag) == item.get("trigger_flag_value"):
                should_fire = True

            # Check delay (simplified: delay_years means fire after N years from enqueue)
            # For now, we track this via a simple counter stored in the item
            if not should_fire:
                delay_years = item.get("delay_years", 0)
                delay_seasons = item.get("delay_seasons", 0)
                if delay_years > 0 or delay_seasons > 0:
                    # Decrement delays
                    if delay_seasons > 0:
                        item["delay_seasons"] = delay_seasons - 1
                    elif delay_years > 0:
                        item["delay_years"] = delay_years - 1
                        item["delay_seasons"] = 3  # One year = 4 seasons, so 3 more after this one
                    if item["delay_years"] <= 0 and item["delay_seasons"] <= 0:
                        should_fire = True

            if should_fire:
                item["fired"] = True
                ready.append(item["event"])
            else:
                still_pending.append(item)

        self.queue = still_pending
        return ready

    def has_pending(self) -> bool:
        """Check if there are any pending events in the queue."""
        return any(not item.get("fired") for item in self.queue)

    def clear(self) -> None:
        """Clear all events from the queue."""
        self.queue.clear()

    def to_dict(self) -> list[dict[str, Any]]:
        """Serialize the queue for saving."""
        return [
            {
                "event": item["event"],
                "delay_years": item.get("delay_years", 0),
                "delay_seasons": item.get("delay_seasons", 0),
                "trigger_age": item.get("trigger_age"),
                "trigger_flag": item.get("trigger_flag"),
                "trigger_flag_value": item.get("trigger_flag_value"),
                "fired": item.get("fired", False),
            }
            for item in self.queue
        ]

    @classmethod
    def from_dict(cls, data: list[dict[str, Any]]) -> "EventQueue":
        """Recreate a queue from serialized data."""
        queue = cls()
        for item in data:
            queue.queue.append({
                "event": item.get("event", {}),
                "delay_years": item.get("delay_years", 0),
                "delay_seasons": item.get("delay_seasons", 0),
                "trigger_age": item.get("trigger_age"),
                "trigger_flag": item.get("trigger_flag"),
                "trigger_flag_value": item.get("trigger_flag_value", True),
                "enqueued_at": time.time(),
                "fired": item.get("fired", False),
            })
        return queue