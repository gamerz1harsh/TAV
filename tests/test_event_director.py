"""Tests for the Event Director (V1) deterministic scoring system."""
import unittest

from event_director import score_event, select_event, DIRECTOR_LOG


class EventDirectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = [
            {
                "id": "extra_shift",
                "title": "An extra shift",
                "weight": 3,
                "requires": {"location": "cafe", "npc": {"priya": {"trust": 1}}},
                "tags": ["cafe", "money", "priya"],
            },
            {
                "id": "study_group",
                "title": "An open seat",
                "weight": 3,
                "requires": {"location": "college"},
                "tags": ["study", "leo", "skill"],
            },
            {
                "id": "quiet_weekend",
                "title": "A quiet weekend",
                "weight": 2,
                "requires": {},
                "tags": ["rest", "energy"],
            },
        ]
        self.context = {
            "player": {"location": "cafe", "stats": {"energy": 2, "money": 1, "skill": 1, "reputation": 1}},
            "npcs": [{"id": "priya", "trust": 2, "affinity": 1}],
            "flags": {"cafe_shift": True},
            "origin": {"id": "cafe_worker"},
            "seen_random_events": [],
            "season_index": 1,
        }

    def test_score_event_returns_float(self) -> None:
        score = score_event(self.events[0], self.context, set())
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)

    def test_score_event_prefers_relevant_events(self) -> None:
        cafe_score = score_event(self.events[0], self.context, set())
        quiet_score = score_event(self.events[2], self.context, set())
        # Cafe event should score higher since player is at cafe with relevant flags
        self.assertGreater(cafe_score, quiet_score)

    def test_score_event_penalizes_recently_seen(self) -> None:
        recent_ids = {"extra_shift"}
        with_penalty = score_event(self.events[0], self.context, recent_ids)
        without_penalty = score_event(self.events[0], self.context, set())
        self.assertLess(with_penalty, without_penalty)

    def test_select_event_returns_highest_scored(self) -> None:
        selected = select_event(self.events, self.context)
        self.assertIsNotNone(selected)
        self.assertIn(selected["id"], [e["id"] for e in self.events])

    def test_select_event_returns_none_for_empty_list(self) -> None:
        self.assertIsNone(select_event([], self.context))

    def test_select_event_logs_to_director_log(self) -> None:
        # Clear the log
        if DIRECTOR_LOG.exists():
            DIRECTOR_LOG.write_text("", encoding="utf-8")
        select_event(self.events, self.context)
        self.assertTrue(DIRECTOR_LOG.exists())
        content = DIRECTOR_LOG.read_text(encoding="utf-8")
        self.assertIn("extra_shift", content)
        self.assertIn("study_group", content)


if __name__ == "__main__":
    unittest.main()
