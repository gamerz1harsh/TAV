"""Structured memory storage and retrieval for Riverton.

Memories are stored as JSONL records with structured fields for tagging,
importance, and entity linking. Retrieval uses multi-stage ranking:
1. Exact entity and tag match
2. Recency and importance ranking
3. BM25 text retrieval (future)
"""
from __future__ import annotations

import json
import re
import string
from collections import Counter
from datetime import datetime
from math import log
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
MEMORIES_FILE = ROOT / "data" / "memories.jsonl"


def _default_memory_id() -> str:
    return f"mem_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def _ensure_file() -> None:
    MEMORIES_FILE.parent.mkdir(exist_ok=True)
    if not MEMORIES_FILE.exists():
        MEMORIES_FILE.write_text("", encoding="utf-8")


# ----- Tokenizer for BM25 -----


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, filter short tokens."""
    text = text.lower()
    tokens = re.split(r"[^a-zA-Z0-9]+", text)
    return [t for t in tokens if len(t) > 2]


# ----- Memory CRUD -----


def add_memory(
    text: str,
    tags: list[str] | None = None,
    linked_entities: list[str] | None = None,
    importance: int = 1,
    season: str | None = None,
) -> dict[str, Any]:
    """Add a structured memory record and return it.

    Args:
        text: The memory text.
        tags: Category tags (e.g., ["cafe", "trust", "priya"]).
        linked_entities: Entity IDs linked to this memory (e.g., ["player", "priya"]).
        importance: 1 (ordinary) to 5 (critical).
        season: The season name when this memory was created.

    Returns:
        The created memory dictionary.
    """
    _ensure_file()
    memory = {
        "id": _default_memory_id(),
        "season": season or "Unknown",
        "timestamp": datetime.now().isoformat(),
        "text": text,
        "tags": tags or [],
        "linked_entities": linked_entities or [],
        "importance": max(1, min(5, importance)),
    }
    with open(MEMORIES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(memory) + "\n")
    return memory


def load_all_memories() -> list[dict[str, Any]]:
    """Load all memory records from the JSONL file."""
    _ensure_file()
    memories: list[dict[str, Any]] = []
    try:
        with open(MEMORIES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        memories.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        pass
    return memories


def clear_memories() -> None:
    """Clear all stored memories (for testing or new game)."""
    _ensure_file()
    MEMORIES_FILE.write_text("", encoding="utf-8")


# ----- Retrieval -----


def retrieve_memories(
    query_tags: list[str] | None = None,
    query_entities: list[str] | None = None,
    query_text: str | None = None,
    max_results: int = 10,
    boost_recent: bool = True,
) -> list[dict[str, Any]]:
    """Retrieve memories using multi-stage ranking.

    Ranking stages:
    1. Exact tag match (+3 per matching tag)
    2. Entity match (+2 per matching entity)
    3. Importance (+importance value)
    4. Recency bonus (+1 for recent memories, up to +3)
    5. BM25 text score (if query_text provided)

    Args:
        query_tags: Required tags to match.
        query_entities: Required entity IDs to match.
        query_text: Free-text query for BM25 scoring.
        max_results: Maximum number of memories to return.
        boost_recent: Whether to add recency bonus.

    Returns:
        Ranked list of memory dictionaries, highest score first.
    """
    memories = load_all_memories()
    if not memories:
        return []

    query_tags = query_tags or []
    query_entities = query_entities or []

    # Precompute BM25 stats if text query provided
    bm25_scores: dict[str, float] = {}
    if query_text:
        query_tokens = _tokenize(query_text)
        if query_tokens:
            bm25_scores = _bm25_score(memories, query_tokens)

    # Filter: if query_tags or query_entities are provided, only include memories with matches
    if query_tags or query_entities:
        filtered: list[dict[str, Any]] = []
        for mem in memories:
            mem_tags = set(mem.get("tags", []))
            mem_entities = set(mem.get("linked_entities", []))
            has_tag_match = query_tags and any(tag in mem_tags for tag in query_tags)
            has_entity_match = query_entities and any(entity in mem_entities for entity in query_entities)
            if has_tag_match or has_entity_match:
                filtered.append(mem)
        memories = filtered

    if not memories:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for mem in memories:
        score = 0.0

        # Tag match
        mem_tags = set(mem.get("tags", []))
        for tag in query_tags:
            if tag in mem_tags:
                score += 3.0

        # Entity match
        mem_entities = set(mem.get("linked_entities", []))
        for entity in query_entities:
            if entity in mem_entities:
                score += 2.0

        # Importance
        score += mem.get("importance", 1)

        # Recency bonus
        if boost_recent:
            try:
                ts = mem.get("timestamp", "")
                dt = datetime.fromisoformat(ts) if ts else datetime.min
                age_hours = (datetime.now() - dt).total_seconds() / 3600
                if age_hours < 1:
                    score += 3.0
                elif age_hours < 24:
                    score += 2.0
                elif age_hours < 168:  # 1 week
                    score += 1.0
            except (ValueError, TypeError):
                pass

        # BM25 text score
        if bm25_scores and mem["id"] in bm25_scores:
            score += bm25_scores[mem["id"]]

        scored.append((score, mem))

    # Sort by score descending
    scored.sort(key=lambda item: item[0], reverse=True)
    return [mem for _, mem in scored[:max_results]]


def _bm25_score(
    memories: list[dict[str, Any]],
    query_tokens: list[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> dict[str, float]:
    """Compute BM25 scores for memories given query tokens.

    BM25 formula:
        score(D, Q) = sum over q in Q of IDF(q) * (f(q,D) * (k1+1)) / (f(q,D) + k1 * (1 - b + b * |D|/avgdl))
    """
    n_docs = len(memories)
    if n_docs == 0:
        return {}

    # Tokenize all documents
    doc_tokens: list[list[str]] = []
    doc_lengths: list[int] = []
    for mem in memories:
        tokens = _tokenize(mem.get("text", ""))
        doc_tokens.append(tokens)
        doc_lengths.append(len(tokens))

    avgdl = sum(doc_lengths) / n_docs if n_docs > 0 else 1.0

    # Document frequency for each query token
    df: dict[str, int] = {}
    for token in query_tokens:
        df[token] = sum(1 for tokens in doc_tokens if token in tokens)

    scores: dict[str, float] = {}
    for idx, mem in enumerate(memories):
        score = 0.0
        doc_len = doc_lengths[idx]
        # Term frequency in this document
        tf = Counter(doc_tokens[idx])
        for token in query_tokens:
            if token not in df or df[token] == 0:
                continue
            idf = log((n_docs - df[token] + 0.5) / (df[token] + 0.5))
            term_freq = tf.get(token, 0)
            numerator = term_freq * (k1 + 1)
            denominator = term_freq + k1 * (1 - b + b * doc_len / avgdl)
            score += idf * (numerator / denominator) if denominator > 0 else 0.0
        scores[mem["id"]] = score
    return scores
