import unittest

from game_features import build_season_summary, filter_memories


class GameFeaturesTests(unittest.TestCase):
    def test_build_season_summary_mentions_key_changes(self) -> None:
        previous = {
            "player": {"stats": {"energy": 5, "money": 4, "skill": 0, "reputation": 0}},
            "npcs": [{"id": "priya", "name": "Priya Shah", "trust": 0, "affinity": 0}],
        }
        current = {
            "player": {"stats": {"energy": 3, "money": 5, "skill": 2, "reputation": 1}},
            "npcs": [{"id": "priya", "name": "Priya Shah", "trust": 1, "affinity": 1}],
        }
        summary = build_season_summary(previous, current, "Study focus")
        self.assertIn("skill", summary.lower())
        self.assertIn("money", summary.lower())
        self.assertIn("priya", summary.lower())

    def test_filter_memories_can_show_recent_only(self) -> None:
        memories = [f"memory {index}" for index in range(8)]
        self.assertEqual(len(filter_memories(memories, "recent")), 6)
        self.assertEqual(len(filter_memories(memories, "all")), 8)


if __name__ == "__main__":
    unittest.main()
