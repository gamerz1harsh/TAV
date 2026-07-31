"""Tests for NPC story arcs and milestone progression."""
import unittest

from npc_arcs import get_npc_arc, get_available_milestones, get_npc_arc_events, NPC_ARCS


class NpcArcsTests(unittest.TestCase):
    def test_get_npc_arc_returns_valid_arc(self):
        arc = get_npc_arc("maya")
        self.assertIsNotNone(arc)
        self.assertEqual(arc["name"], "Maya Ortiz")
        self.assertIn("milestones", arc)

    def test_get_npc_arc_returns_none_for_unknown(self):
        arc = get_npc_arc("unknown_npc")
        self.assertIsNone(arc)

    def test_arc_has_milestones_with_events(self):
        for npc_id, arc in NPC_ARCS.items():
            self.assertGreater(len(arc["milestones"]), 0, f"{npc_id} has no milestones")
            for milestone in arc["milestones"]:
                self.assertIn("id", milestone)
                self.assertIn("trigger", milestone)
                self.assertIn("event", milestone)
                event = milestone["event"]
                self.assertIn("id", event)
                self.assertIn("title", event)
                self.assertIn("choices", event)
                self.assertGreater(len(event["choices"]), 0)

    def test_get_available_milestones_returns_empty_for_no_trigger(self):
        # Maya's affinity_neg2 milestone triggers when affinity >= -2 (always true for neutral values)
        # With trust=0, only the affinity_neg2 milestone should be available
        npc_state = {"trust": 0, "affinity": 0}
        milestones = get_available_milestones("maya", npc_state, {}, set())
        # maya_affinity_neg2 triggers because 0 >= -2 is True
        self.assertEqual(len(milestones), 1)
        self.assertEqual(milestones[0]["id"], "maya_affinity_neg2")

    def test_get_available_milestones_triggers_on_trust(self):
        npc_state = {"trust": 2, "affinity": 0}
        milestones = get_available_milestones("maya", npc_state, {}, set())
        self.assertGreaterEqual(len(milestones), 1)
        self.assertEqual(milestones[0]["id"], "maya_trust_1")

    def test_get_available_milestones_skips_completed(self):
        npc_state = {"trust": 3, "affinity": 0}
        completed = {"maya_trust_1"}
        milestones = get_available_milestones("maya", npc_state, {}, completed)
        self.assertNotIn("maya_trust_1", [m["id"] for m in milestones])

    def test_get_available_milestones_requires_flags(self):
        npc_state = {"trust": 3, "affinity": 0}
        # Leo's trust_3 milestone requires flags ["study_group"]
        milestones = get_available_milestones("leo", npc_state, {}, set())
        self.assertEqual(len(milestones), 1)  # Only trust_2 should trigger
        self.assertEqual(milestones[0]["id"], "leo_trust_2")

    def test_get_available_milestones_with_flags(self):
        npc_state = {"trust": 3, "affinity": 0}
        flags = {"study_group": True}
        milestones = get_available_milestones("leo", npc_state, flags, set())
        self.assertEqual(len(milestones), 2)

    def test_get_npc_arc_events_collects_all_eligible(self):
        npcs = [
            {"id": "maya", "trust": 2, "affinity": 0},
            {"id": "priya", "trust": 2, "affinity": 0},
        ]
        events = get_npc_arc_events(npcs, {}, set())
        # Maya: maya_trust_1 (trust>=2) + maya_affinity_neg2 (0>=-2) = 2
        # Priya: priya_trust_2 (trust>=2) = 1
        # Total: 3
        self.assertEqual(len(events), 3)
        self.assertIn("maya_shares_project", [e["id"] for e in events])
        self.assertIn("priya_offers_shift", [e["id"] for e in events])
        self.assertIn("maya_tension", [e["id"] for e in events])

    def test_get_npc_arc_events_tags_events(self):
        npcs = [{"id": "maya", "trust": 2, "affinity": 0}]
        events = get_npc_arc_events(npcs, {}, set())
        # Maya has 2 eligible milestones: maya_trust_1 and maya_affinity_neg2
        self.assertEqual(len(events), 2)
        # Both events should be tagged with maya's npc_id
        for event in events:
            self.assertEqual(event["npc_id"], "maya")
        # Check that both milestone IDs are present
        milestone_ids = [e["milestone_id"] for e in events]
        self.assertIn("maya_trust_1", milestone_ids)
        self.assertIn("maya_affinity_neg2", milestone_ids)

    def test_nora_negative_affinity_triggers_maya_tension(self):
        npc_state = {"trust": 0, "affinity": -2}
        milestones = get_available_milestones("maya", npc_state, {}, set())
        self.assertGreaterEqual(len(milestones), 1)
        self.assertEqual(milestones[0]["id"], "maya_affinity_neg2")


if __name__ == "__main__":
    unittest.main()
