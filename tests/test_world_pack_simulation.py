"""Tests for the Naruto pack's modular simulation hooks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from api import server as api_server
import game_config
from game_engine import GameEngine, GameRuleError
from world_pack import get_world_pack


class WorldPackSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.game_folder = Path(self.temp_dir.name) / "test-life"
        self.folder_patch = patch("game_engine.game_config.create_game_folder", return_value=self.game_folder)
        self.folder_patch.start()
        self.engine = GameEngine()
        self.engine.new_game(
            "Test Shinobi",
            "",
            world_pack_id="naruto",
            world_options={"age": 8, "village": "leaf", "clan": "civilian", "chakra_nature": "wind"},
        )

    def tearDown(self) -> None:
        self.folder_patch.stop()
        self.temp_dir.cleanup()

    def test_opportunity_is_action_triggered_costed_and_persistent(self) -> None:
        self.engine.travel_world_location("academy")
        self.engine.perform_world_action("academy_study")
        self.assertEqual(self.engine.public_state()["world_opportunities"], [])
        state = self.engine.perform_world_action("academy_study")
        event = state["world_opportunities"][0]
        self.assertEqual(event["id"], "instructor_after_hours")

        self.engine.state["personal_actions_remaining"] = 0
        with self.assertRaises(GameRuleError):
            self.engine.resolve_world_opportunity(event["id"], "stay_for_lesson")
        self.assertEqual(len(self.engine.public_state()["world_opportunities"]), 1)

        self.engine.state["personal_actions_remaining"] = 3
        before = self.engine.public_state()["naruto"]["attributes"]["academy_knowledge"]
        state = self.engine.resolve_world_opportunity(event["id"], "stay_for_lesson")
        self.assertEqual(state["naruto"]["attributes"]["academy_knowledge"], before + 3)
        self.assertEqual(state["personal_actions_remaining"], 2)
        self.assertEqual(state["world_opportunities"], [])

        reloaded = GameEngine()
        state = reloaded.load_game(self.game_folder)
        self.assertEqual(state["world"]["opportunities_resolved"][-1]["choice_id"], "stay_for_lesson")

    def test_regional_prosperity_changes_shop_prices_and_wages(self) -> None:
        pack = get_world_pack("naruto")
        shop = self.engine._active_region_shop(pack)
        item = shop["items"][0]
        world = self.engine.state["world"]
        world["region_state"]["land_of_fire"]["prosperity"] = 100
        self.assertLess(self.engine._market_price(item, shop, pack), item["price"])
        self.assertGreater(self.engine._regional_economy_value(100, "market_street", pack), 100)
        self.engine.travel_world_location("market_street")
        state = self.engine.public_state()
        displayed = next(row for row in state["world_shop"]["items"] if row["id"] == item["id"])
        self.assertEqual(displayed["price"], self.engine._market_price(item, shop, pack))
        starting_money = state["world_wallet"]
        state = self.engine.purchase_world_item(item["id"])
        self.assertEqual(state["world_wallet"], starting_money - displayed["price"])

    def test_naruto_pack_event_definitions_are_valid_and_modular(self) -> None:
        pack = get_world_pack("naruto")
        self.assertEqual(pack["manifest"]["version"], 4)
        self.assertEqual(len(pack["events"]["opportunities"]), 2)
        self.assertIn("events.json", pack["manifest"]["files"])

    def test_every_chakra_release_has_fifty_techniques_across_all_tiers(self) -> None:
        pack = get_world_pack("naruto")
        expected_tiers = {1: 6, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 5, 9: 3}
        for nature in ("wind", "fire", "water", "earth", "lightning", "sand", "ice", "yin", "yang"):
            with self.subTest(nature=nature):
                styles = [
                    item for item in pack["progression"]["techniques"]
                    if str(item.get("id", "")).startswith(f"{nature}_release_t")
                ]
                self.assertEqual(len(styles), 50)
                self.assertEqual(
                    {tier: sum(item.get("tier") == tier for item in styles) for tier in range(1, 10)},
                    expected_tiers,
                )
                self.assertTrue(all(item.get("learn_requirements") for item in styles))

    def test_birth_traits_include_rarity_tiers_and_unique_sharingan(self) -> None:
        pack = get_world_pack("naruto")
        traits = pack["traits"]["traits"]
        rarity_tiers = {item.get("rarity") for item in traits}
        sharingan = next(item for item in traits if item["id"] == "dormant_sharingan_spark")

        self.assertGreaterEqual(len(traits), 50)
        self.assertTrue({"common", "rare", "epic", "legendary", "unique", "secret"} <= rarity_tiers)
        self.assertEqual(sharingan["rarity"], "unique")
        self.assertGreater(sharingan["modifiers"]["combat_power_percent"], 0)

    def test_age_five_ceremony_can_reveal_all_declared_natures(self) -> None:
        pack = get_world_pack("naruto")
        expected_natures = {item["id"] for item in pack["character_creation"]["chakra_natures"]}
        self.assertTrue({"sand", "ice", "yin", "yang"} <= expected_natures)
        with patch("game_engine.generate_world_event_narration", return_value=None):
            self.engine.new_game(
                "Young Shinobi", "", world_pack_id="naruto",
                world_options={"age": 4, "village": "leaf", "clan": "civilian"},
            )
            self.assertFalse(self.engine._naruto_profile()["nature_ceremony_complete"])
            state = self.engine.advance_world_year()

        self.assertEqual(state["player"]["age"], 5)
        self.assertTrue(state["naruto"]["nature_ceremony_complete"])
        self.assertIn(state["naruto"]["chakra_nature"]["id"], expected_natures)
        self.assertEqual(state["world_nature_ceremony"]["nature"], state["naruto"]["chakra_nature"]["name"])

    def test_training_rolls_variable_gains_and_doubles_critical_success(self) -> None:
        self.engine._naruto_profile()["traits"] = []
        self.engine.travel_world_location("training_ground")
        with patch("game_engine.random.randint", return_value=3), patch("game_engine.random.random", return_value=0.01):
            state = self.engine.perform_world_action("train_chakra_control")

        result = state["world_last_action_result"]
        self.assertTrue(result["critical"])
        self.assertEqual(result["critical_chance"], 8)
        self.assertEqual(result["attribute_gains"]["chakra_control"], 6)
        self.assertEqual(result["skill_xp_gains"]["ninjutsu"], 6)

    def test_recommendations_hide_basic_chakra_training_after_level_fifty(self) -> None:
        profile = self.engine._naruto_profile()
        profile["attributes"]["chakra_control"] = 50
        profile["skills"]["ninjutsu"] = 50
        self.engine.travel_world_location("training_ground")

        recommendations = self.engine._recommended_world_actions()
        self.assertNotIn("train_chakra_control", {item["id"] for item in recommendations})

    def test_legacy_save_migration_repairs_map_and_keeps_npc_memories(self) -> None:
        pack = get_world_pack("naruto")
        legacy_naruto = next(
            item for item in pack["people"]["people"] if item["id"] == "naruto_uzumaki"
        ).copy()
        legacy_naruto["location"] = "academy"
        legacy_naruto.pop("local_location", None)
        legacy_naruto.pop("region_id", None)
        legacy_naruto["affinity"] = 37
        legacy_naruto["memories"] = ["They remember the promise you made."]
        self.engine.state["npcs"] = self.engine.state["npcs"][:3] + [legacy_naruto]
        self.engine.state["world"].pop("current_region", None)
        self.engine.state["world"]["region_state"] = {"land_of_fire": None}
        self.engine.state["world"]["action_counts"] = None
        self.engine.state["world"]["opportunities_pending"] = None
        self.engine.state["world"]["quests"] = {}
        self.engine.state["world"]["organizations"] = []
        self.engine.state["world"]["active_encounter"] = "invalid"

        self.engine._ensure_progression_defaults()
        state = self.engine.public_state()
        migrated = next(item for item in self.engine.state["npcs"] if item["id"] == "naruto_uzumaki")
        public_naruto = next(item for item in state["world_people"] if item["id"] == "naruto_uzumaki")

        self.assertEqual(state["world_state"]["current_region"], "land_of_fire")
        self.assertEqual(state["world_state"]["home_region"], "land_of_fire")
        self.assertEqual(migrated["location"], "academy_leaf")
        self.assertEqual(public_naruto["location"], "academy")
        self.assertEqual(migrated["affinity"], 37)
        self.assertEqual(migrated["memories"], ["They remember the promise you made."])
        self.assertGreaterEqual(len(state["world_people"]), len(pack["people"]["people"]))
        self.assertEqual(state["world_state"]["region_state"]["land_of_fire"]["security"], 52)
        self.assertEqual(state["world_state"]["action_counts"], {})
        self.assertEqual(state["world_state"]["opportunities_pending"], [])
        self.assertEqual(state["world_state"]["quests"], [])
        self.assertEqual(state["world_state"]["active_encounter"], None)

        self.engine.state["world"]["current_region"] = "land_of_wind"
        relocated = next(
            item for item in self.engine.public_state()["world_people"] if item["id"] == "naruto_uzumaki"
        )
        self.assertEqual(relocated["location"], "academy_leaf")

    def test_sand_start_gets_local_facilities_and_village_instructor(self) -> None:
        self.engine.new_game(
            "Sand Shinobi",
            "",
            world_pack_id="naruto",
            world_options={"age": 8, "village": "sand", "clan": "civilian", "chakra_nature": "wind"},
        )
        state = self.engine.public_state()
        academy = next(place for place in state["world_places"] if place["id"] == "academy")
        self.assertEqual(state["world_state"]["current_region"], "land_of_wind")
        self.assertEqual(state["world_state"]["home_region"], "land_of_wind")
        self.assertEqual(academy["name"], "Hidden Sand Academy")
        self.assertEqual(academy["region_id"], "land_of_wind")
        self.assertFalse(any(place["id"].endswith("_leaf") for place in state["world_places"]))
        guardian = next(person for person in state["world_people_present"] if person["id"] == "family_guardian")
        self.assertEqual(guardian["location"], "home")

        state = self.engine.travel_world_location("academy")
        present_ids = {person["id"] for person in state["world_people_present"]}
        self.assertIn("academy_instructor", present_ids)
        self.assertNotIn("naruto_uzumaki", present_ids)
        study = next(action for action in state["world_actions"] if action["id"] == "academy_study")
        self.assertTrue(study["available"])
        state = self.engine.perform_world_action("academy_study")
        self.assertGreater(state["naruto"]["attributes"]["academy_knowledge"], 0)

    def test_skill_tree_is_clan_gated_and_mode_changes_effective_stats(self) -> None:
        self.engine.new_game(
            "Uchiha Shinobi", "", world_pack_id="naruto",
            world_options={"age": 12, "village": "leaf", "clan": "uchiha", "chakra_nature": "fire"},
        )
        profile = self.engine._naruto_profile()
        profile["skill_points"] = 2
        profile["attributes"].update({"willpower": 30, "agility": 24})
        profile["skills"]["taijutsu"] = 8
        self.engine.state["personal_actions_remaining"] = 3
        tree_state = self.engine.public_state()["world_skill_trees"]
        character_tree = next(tree for tree in tree_state if tree["id"] == "character")
        visible_nodes = {node["id"] for node in character_tree["nodes"]}
        self.assertIn("sharingan_1_tomoe", visible_nodes)
        self.assertNotIn("hyuga_gentle_fist", visible_nodes)
        sharingan = next(node for node in character_tree["nodes"] if node["id"] == "sharingan_1_tomoe")
        self.assertTrue(sharingan["available"])

        self.engine.learn_world_skill_node("sharingan_1_tomoe")
        before = self.engine.public_state()["effective_attributes"]["agility"]
        self.engine.toggle_world_mode("sharingan", True)
        after = self.engine.public_state()["effective_attributes"]["agility"]
        self.assertEqual(after, before + 4)
        self.assertTrue(self.engine.public_state()["naruto"]["modes"]["sharingan"]["active"])
        self.assertIn("sharingan_insight", {item["id"] for item in self.engine.public_state()["naruto"]["techniques"]})

    def test_hyuga_tree_grants_toggleable_passive_and_mode_tier_scales(self) -> None:
        self.engine.new_game(
            "Hyuga Shinobi", "", world_pack_id="naruto",
            world_options={"age": 12, "village": "leaf", "clan": "hyuga", "chakra_nature": "water"},
        )
        profile = self.engine._naruto_profile()
        profile["skill_points"] = 2
        profile["attributes"].update({"chakra_control": 30, "willpower": 24})
        self.engine.state["personal_actions_remaining"] = 3
        self.engine.learn_world_skill_node("byakugan_awareness")
        passive = next(item for item in profile["techniques"] if item["id"] == "byakugan_field_awareness")
        self.assertEqual(passive["type"], "passive")
        self.assertTrue(passive["active"])
        base_intelligence = profile["attributes"]["intelligence"]
        self.assertEqual(self.engine.public_state()["effective_attributes"]["intelligence"], base_intelligence + 2)

        self.engine.toggle_passive_technique("byakugan_field_awareness", False)
        self.assertEqual(self.engine.public_state()["effective_attributes"]["intelligence"], base_intelligence)
        mode = profile["modes"]["byakugan"]
        mode["active"] = True
        mode["tier"] = 3
        tier_two_power = self.engine._combat_power(profile)
        mode["tier"] = 2
        self.assertEqual(tier_two_power - self.engine._combat_power(profile), 5)

    def test_practicing_technique_levels_it_and_adds_a_small_stat_bonus(self) -> None:
        profile = self.engine._naruto_profile()
        profile["attributes"]["chakra_capacity"] = 100
        profile["chakra_current"] = 100
        self.engine._apply_naruto_effects({"learn_technique": "fireball_jutsu"})
        self.engine.state["personal_actions_remaining"] = 7
        profile["traits"] = []
        before = self.engine.public_state()["effective_attributes"]["chakra_control"]
        state = None
        with patch("game_engine.random.randint", return_value=4), patch("game_engine.random.random", return_value=0.99):
            for _ in range(7):
                state = self.engine.perform_world_action("practice_technique_fireball_jutsu")
        technique = next(item for item in state["naruto"]["techniques"] if item["id"] == "fireball_jutsu")
        self.assertEqual(technique["level"], 2)
        self.assertEqual(technique["xp"], 28)
        self.assertEqual(state["effective_attributes"]["chakra_control"], before + 1)

    def test_regional_equipment_can_be_equipped_and_forged(self) -> None:
        self.engine.state["player"]["stats"]["money"] = 500
        self.engine.travel_world_location("market_street")
        self.engine.purchase_world_item("leaf_kunai")
        self.engine.purchase_world_item("iron_ingot")
        gear = next(item for item in self.engine._naruto_profile()["inventory"] if item["id"] == "leaf_kunai")
        state = self.engine.equip_world_item(gear["instance_id"])
        base_strength = self.engine._naruto_profile()["attributes"]["strength"]
        self.assertEqual(state["effective_attributes"]["strength"], base_strength + 1)
        self.engine.travel_world_location("blacksmith")
        before_actions = self.engine.state["personal_actions_remaining"]
        state = self.engine.forge_world_item(gear["instance_id"])
        updated = next(item for item in state["naruto"]["inventory"] if item["instance_id"] == gear["instance_id"])
        self.assertIn(updated["tier"], {1, 2})
        self.assertEqual(state["personal_actions_remaining"], before_actions - 1)
        self.assertIsNotNone(state["world_last_forge"])

    def test_shop_stock_changes_with_region(self) -> None:
        leaf_items = {item["name"] for item in self.engine.public_state()["world_shop"]["items"]}
        self.engine.new_game(
            "Sand Shinobi", "", world_pack_id="naruto",
            world_options={"age": 8, "village": "sand", "clan": "civilian", "chakra_nature": "wind"},
        )
        sand_items = {item["name"] for item in self.engine.public_state()["world_shop"]["items"]}
        self.assertIn("Sunagakure Tool Exchange", self.engine.public_state()["world_shop"]["name"])
        self.assertNotEqual(leaf_items, sand_items)

    def test_blacksmith_training_unlocks_a_conversation_hired_career(self) -> None:
        self.engine.state["player"]["age"] = 16
        self.engine.state["world"]["rank"] = "Academy Student"
        self.engine.state["personal_actions_remaining"] = 7
        self.engine.travel_world_location("blacksmith")
        with patch("game_engine.random.randint", return_value=4), patch("game_engine.random.random", return_value=0.99):
            for _ in range(5):
                self.engine.perform_world_action("smithing_practice")
        self.assertEqual(self.engine._naruto_profile()["skills"]["smithing"], 2)

        with patch("game_engine.generate_npc_dialogue", return_value=None):
            state = self.engine.talk_to_world_npc("village_smith", "Could I apply for the smithing job?")
        self.assertEqual(state["world_careers"]["active"]["job_id"], "village_smith")
        state = self.engine.work_world_job()
        self.assertEqual(state["world_careers"]["active"]["experience"], 1)
        self.assertGreater(state["naruto"]["skill_xp"]["smithing"], 20)

    def test_nature_matchup_changes_combat_forecast(self) -> None:
        self.engine.new_game(
            "Fire Shinobi", "", world_pack_id="naruto",
            world_options={"age": 8, "village": "leaf", "clan": "civilian", "chakra_nature": "fire"},
        )
        self.engine.travel_world_location("training_ground")
        state = self.engine.start_world_combat("academy_spar")
        fight = state["world_combat"]
        self.assertEqual(fight["nature_advantage"], 1)
        advantaged = fight["player_win_probability"]
        neutral = self.engine._combat_win_probability(self.engine._combat_power(self.engine._naruto_profile()), fight["opponent_power"], 0)
        self.assertGreater(advantaged, neutral)

    def test_child_legacy_continuation_uses_a_new_save_and_keeps_world_memories(self) -> None:
        player = self.engine.state["player"]
        player["age"] = 18
        player["life_stage"] = "adult"
        self.engine.state["personal_actions_remaining"] = 3
        self.engine.state["social_actions_remaining"] = 2
        partner = next(npc for npc in self.engine.state["npcs"] if npc["id"] == "academy_peer")
        partner.update({"age": 18, "affinity": 30, "trust": 30})
        self.engine.travel_world_location("academy")
        parent_state = self.engine.start_world_legacy_family(partner["id"], "Hana Shinobi")
        heir = parent_state["world_legacy"]["heirs"][0]
        self.assertEqual(parent_state["social_actions_remaining"], 1)

        created = []
        def create_next_folder(name: str) -> Path:
            folder = Path(self.temp_dir.name) / f"generation-{len(created) + 1}"
            folder.mkdir()
            created.append(folder)
            return folder

        with patch("game_engine.game_config.create_game_folder", side_effect=create_next_folder):
            child_state = self.engine.continue_world_as_heir(heir["id"])

        self.assertEqual(child_state["player"]["name"], "Hana Shinobi")
        self.assertEqual(child_state["player"]["age"], 0)
        self.assertEqual(child_state["world_legacy"]["generation"], 2)
        self.assertEqual(child_state["world_legacy"]["generations"][-1]["continued_as"], "child")
        parent_npcs = [npc for npc in child_state["world_people"] if npc["role"] == "Parent"]
        self.assertGreaterEqual(len(parent_npcs), 2)
        other_parent = next(npc for npc in parent_npcs if npc["id"] == heir["partner_id"])
        self.assertIn("Hana Shinobi", " ".join(other_parent["memories"]))
        previous_life = GameEngine().load_game(self.game_folder)
        self.assertEqual(previous_life["player"]["age"], 18)
        self.assertEqual(previous_life["world_legacy"]["heirs"][0]["status"], "continued")

    def test_game_folder_creation_avoids_same_second_name_collisions(self) -> None:
        self.folder_patch.stop()
        with tempfile.TemporaryDirectory() as temporary:
            fixed_time = Mock()
            fixed_time.strftime.return_value = "20261024_120000"
            with patch.object(game_config, "GAMES_DIR", Path(temporary)), patch.object(game_config, "datetime") as date_mock:
                date_mock.now.return_value = fixed_time
                first = game_config.create_game_folder("Legacy Child")
                second = game_config.create_game_folder("Legacy Child")
                self.assertNotEqual(first, second)
                self.assertTrue(first.is_dir())
                self.assertTrue(second.is_dir())
        self.folder_patch.start()

    def test_free_npc_chat_can_offer_a_pack_quest_without_spending_actions(self) -> None:
        self.engine.travel_world_location("academy")
        before = self.engine.public_state()
        with patch("game_engine.generate_npc_dialogue", return_value=None):
            state = self.engine.talk_to_world_npc(
                "academy_instructor", "Could you help me find a small academy mission?"
            )

        quest = next(item for item in state["world_quests"] if item["status"] == "offered")
        instructor = next(item for item in self.engine.state["npcs"] if item["id"] == "academy_instructor")
        self.assertEqual(quest["template_id"], "academy_delivery")
        self.assertEqual(state["personal_actions_remaining"], before["personal_actions_remaining"])
        self.assertEqual(state["social_actions_remaining"], before["social_actions_remaining"])
        self.assertEqual(state["world_last_chat"]["quest_id"], quest["id"])
        self.assertTrue(any("talked about" in memory for memory in instructor["memories"]))

    def test_public_state_endpoint_treats_fresh_launch_as_empty_state(self) -> None:
        engine_without_life = Mock()
        engine_without_life.public_state.side_effect = GameRuleError("Start or load a game first.")
        with patch("api.server.get_engine", return_value=engine_without_life):
            response = api_server.app.test_client().get("/api/public_state")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["state"])


if __name__ == "__main__":
    unittest.main()
