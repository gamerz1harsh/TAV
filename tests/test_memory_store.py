"""Tests for the structured memory storage and retrieval system."""
import unittest
import tempfile
import os
from pathlib import Path

from memory_store import add_memory, load_all_memories, clear_memories, retrieve_memories


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        # Use a temporary directory for test data
        self.temp_dir = tempfile.mkdtemp()
        self.original_root = None
        # We'll override the ROOT path by setting the path directly
        import memory_store
        self.original_memories_file = memory_store.MEMORIES_FILE
        memory_store.MEMORIES_FILE = Path(self.temp_dir) / "memories.jsonl"
        # Clear any existing data
        clear_memories()

    def tearDown(self):
        import memory_store
        memory_store.MEMORIES_FILE = self.original_memories_file
        # Clean up temp files
        for f in Path(self.temp_dir).glob("*"):
            f.unlink()
        os.rmdir(self.temp_dir)

    def test_add_memory_creates_entry(self):
        add_memory(
            text="A quiet morning at the cafe.",
            tags=["cafe", "morning"],
            linked_entities=["priya"],
            importance=2,
            season="Spring",
        )
        memories = load_all_memories()
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["text"], "A quiet morning at the cafe.")
        self.assertEqual(memories[0]["importance"], 2)

    def test_add_memory_assigns_unique_id(self):
        add_memory("First memory.")
        add_memory("Second memory.")
        memories = load_all_memories()
        self.assertEqual(len(memories), 2)
        self.assertNotEqual(memories[0]["id"], memories[1]["id"])

    def test_retrieve_memories_by_tag(self):
        add_memory("Cafe work.", tags=["cafe", "work"], linked_entities=["priya"], importance=2, season="Spring")
        add_memory("Study session.", tags=["study", "college"], linked_entities=["leo"], importance=1, season="Spring")
        add_memory("Another cafe day.", tags=["cafe", "relax"], linked_entities=["priya"], importance=1, season="Summer")

        results = retrieve_memories(query_tags=["cafe"], max_results=5)
        self.assertEqual(len(results), 2)
        # Both cafe memories should be returned
        self.assertTrue(any("Cafe work" in r["text"] for r in results))
        self.assertTrue(any("Another cafe day" in r["text"] for r in results))

    def test_retrieve_memories_by_entity(self):
        add_memory("Walk with Sam.", tags=["community"], linked_entities=["sam"], importance=3, season="Spring")
        add_memory("Coffee with Priya.", tags=["cafe"], linked_entities=["priya"], importance=2, season="Summer")

        results = retrieve_memories(query_entities=["sam"], max_results=5)
        self.assertEqual(len(results), 1)
        self.assertIn("Sam", results[0]["text"])

    def test_retrieve_memories_ranks_by_importance(self):
        add_memory("Low importance.", tags=["test"], importance=1, season="Spring")
        add_memory("High importance.", tags=["test"], importance=5, season="Spring")
        add_memory("Medium importance.", tags=["test"], importance=3, season="Spring")

        results = retrieve_memories(query_tags=["test"], max_results=3)
        # Should be sorted by importance descending
        self.assertEqual(results[0]["importance"], 5)
        self.assertEqual(results[1]["importance"], 3)
        self.assertEqual(results[2]["importance"], 1)

    def test_retrieve_memories_limits_top_k(self):
        for i in range(5):
            add_memory(f"Memory {i}.", tags=["test"], importance=1, season="Spring")

        results = retrieve_memories(query_tags=["test"], max_results=3)
        self.assertEqual(len(results), 3)

    def test_clear_memories_removes_all(self):
        add_memory("Something to remember.", tags=["test"], importance=1, season="Spring")
        clear_memories()
        memories = load_all_memories()
        self.assertEqual(len(memories), 0)


if __name__ == "__main__":
    unittest.main()
