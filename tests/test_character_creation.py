import unittest

from character_creation import build_character_template, enumerate_eras, validate_era


class CharacterCreationTests(unittest.TestCase):
    def test_enumerate_eras_contains_modern(self):
        eras = enumerate_eras()
        self.assertIn("modern", eras)

    def test_validate_era(self):
        self.assertTrue(validate_era("modern"))
        self.assertFalse(validate_era("unknown-era"))

    def test_build_character_template_defaults(self):
        template = build_character_template("alex")
        self.assertIn("player", template)
        player = template["player"]
        self.assertEqual(player["name"], "Alex")
        self.assertIn("stats", player)
        self.assertIn("ui_stats", player)


if __name__ == "__main__":
    unittest.main()
