import unittest

from llm_service import should_use_async_llm, build_async_payload


class AsyncLlmTests(unittest.TestCase):
    def test_should_use_async_llm_defaults_to_true(self) -> None:
        self.assertTrue(should_use_async_llm())

    def test_build_async_payload_contains_mode(self) -> None:
        payload = build_async_payload({"player": {"location": "cafe"}}, "demo")
        self.assertIn("mode", payload)
        self.assertEqual(payload["mode"], "async")


if __name__ == "__main__":
    unittest.main()
