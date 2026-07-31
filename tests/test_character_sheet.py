import unittest

from game_features import build_character_sheet_data


class CharacterSheetTests(unittest.TestCase):
    def test_build_character_sheet_data_includes_relationships_and_paths(self) -> None:
        state = {
            "player": {
                "name": "Ava",
                "location": "cafe",
                "stats": {"energy": 3, "money": 5, "skill": 2, "reputation": 1},
            },
            "npcs": [
                {"id": "priya", "name": "Priya Shah", "trust": 2, "affinity": 3},
                {"id": "sam", "name": "Sam Walker", "trust": 1, "affinity": 1},
            ],
            "flags": {"cafe_shift": True},
            "opportunities": [{"name": "Cafe route", "hint": "More shifts."}],
            "season_summary": "This season mattered.",
        }
        sheet = build_character_sheet_data(state)
        self.assertEqual(sheet["name"], "Ava")
        self.assertEqual(sheet["relationships"][0]["name"], "Priya Shah")
        self.assertTrue(any(item["name"] == "Cafe route" for item in sheet["paths"]))


if __name__ == "__main__":
    unittest.main()
