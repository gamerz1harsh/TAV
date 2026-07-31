import unittest

from llm_service import _candidate_endpoints, build_fallback_options, parse_llm_response


class LlmServiceTests(unittest.TestCase):
    def test_parse_llm_response_strips_code_fences(self) -> None:
        payload = '''```json
{"options":[{"id":"study","label":"Study harder","description":"Push your work forward.","effects":{"skill":1,"energy":-1}}]}
```'''
        parsed = parse_llm_response(payload)
        self.assertEqual(parsed["options"][0]["id"], "study")

    def test_parse_llm_response_handles_comments_and_markers(self) -> None:
        payload = '''<channel|>```json
{
  // a comment from the model
  "scenario": "A small apartment morning",
  "map": {"areas": [{"name": "Kitchen"}]},
  "npcs": []
}
```'''
        parsed = parse_llm_response(payload)
        self.assertEqual(parsed["scenario"], "A small apartment morning")

    def test_build_fallback_options_uses_state_context(self) -> None:
        state = {
            "player": {
                "location": "cafe",
                "stats": {"energy": 2, "money": 1, "skill": 0, "reputation": 1},
            },
            "npcs": [{"id": "priya", "trust": 2, "affinity": 1}],
            "flags": {"cafe_shift": True},
        }
        options = build_fallback_options(state)
        self.assertGreaterEqual(len(options), 2)
        self.assertTrue(any(option["id"] == "cafe_focus" for option in options))

    def test_candidate_endpoints_include_lm_studio_style_paths(self) -> None:
        endpoints = _candidate_endpoints("http://127.0.0.1:59000")
        self.assertIn("http://127.0.0.1:59000/v1/chat/completions", endpoints)
        self.assertIn("http://127.0.0.1:59000/chat/completions", endpoints)


if __name__ == "__main__":
    unittest.main()
