#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
test_memory_retriever.py — Unit tests for memory_retriever.py.

Tests the pure-Python cosine similarity engine and MemoryRetriever class.
All tests use in-memory fixture data — no files are read from disk
and no third-party libraries are required.
"""

import json
import math
import os
import sys
import tempfile
import unittest

# Ensure scripts/ is resolvable from tests/
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from memory_retriever import MemoryRetriever, RetrievalResult, cosine_similarity
from memory_schemas import (
    SCHEMA_VERSION,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    EMBEDDING_DIM,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _unit_vec(index: int, dim: int = EMBEDDING_DIM) -> list[float]:
    """Return a unit vector with 1.0 at position `index` and 0.0 elsewhere."""
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


def _make_embedding_envelope(records: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "model_name": EMBEDDING_MODEL_NAME,
        "model_version": EMBEDDING_MODEL_VERSION,
        "generated_at": "2026-02-27T13:00:00Z",
        "embeddings": records,
    }


def _write_embeddings(directory: str, filename: str, records: list[dict]) -> None:
    os.makedirs(os.path.join(directory, "embeddings"), exist_ok=True)
    path = os.path.join(directory, "embeddings", filename)
    with open(path, "w") as fh:
        json.dump(_make_embedding_envelope(records), fh)


# ---------------------------------------------------------------------------
# Tests: cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity(unittest.TestCase):

    def test_identical_unit_vectors_return_one(self):
        """Cosine similarity of a vector with itself must be exactly 1.0."""
        vec = _unit_vec(0)
        result = cosine_similarity(vec, vec)
        self.assertAlmostEqual(result, 1.0, places=9)

    def test_orthogonal_vectors_return_zero(self):
        """Cosine similarity of orthogonal unit vectors must be 0.0."""
        a = _unit_vec(0)
        b = _unit_vec(1)
        result = cosine_similarity(a, b)
        self.assertAlmostEqual(result, 0.0, places=9)

    def test_opposite_unit_vectors_return_negative_one(self):
        """Anti-parallel vectors must return -1.0."""
        a = _unit_vec(0)
        b = [-x for x in a]
        result = cosine_similarity(a, b)
        self.assertAlmostEqual(result, -1.0, places=9)

    def test_zero_vector_returns_zero(self):
        """Zero-vector (zero magnitude) must return 0.0 without division by zero."""
        a = [0.0] * EMBEDDING_DIM
        b = _unit_vec(5)
        result = cosine_similarity(a, b)
        self.assertEqual(result, 0.0)

    def test_dimension_mismatch_returns_zero(self):
        """Mismatched vector dimensions must return 0.0 rather than raising."""
        a = [1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        result = cosine_similarity(a, b)
        self.assertEqual(result, 0.0)

    def test_known_similarity_value(self):
        """Verify against a hand-computed cosine similarity."""
        # a = [1, 0], b = [1, 1] (normalised)
        a = [1.0, 0.0]
        b_raw = [1.0, 1.0]
        mag_b = math.sqrt(2)
        b = [x / mag_b for x in b_raw]
        expected = 1.0 / mag_b  # ≈ 0.7071
        result = cosine_similarity(a, b)
        self.assertAlmostEqual(result, expected, places=9)


# ---------------------------------------------------------------------------
# Tests: MemoryRetriever
# ---------------------------------------------------------------------------

class TestMemoryRetriever(unittest.TestCase):

    def setUp(self):
        """Create a temporary memory directory with fixture embeddings."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.memory_dir = self.tmpdir.name

        # Create three file embedding records with known unit vectors
        self.file_records = [
            {
                "file_path": "scripts/delta_executor.py",
                "hash": "sha256:aaa",
                "chunk_index": 0,
                "total_chunks": 1,
                "embedding": _unit_vec(0),
            },
            {
                "file_path": "scripts/gamma_triage.py",
                "hash": "sha256:bbb",
                "chunk_index": 0,
                "total_chunks": 1,
                "embedding": _unit_vec(1),
            },
            {
                "file_path": "terraform/main.tf",
                "hash": "sha256:ccc",
                "chunk_index": 0,
                "total_chunks": 1,
                "embedding": _unit_vec(2),
            },
        ]
        _write_embeddings(self.memory_dir, "file_embeddings.json", self.file_records)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_top_k_returns_correct_rank_order(self):
        """Top-k results sorted by cosine score: use_weighted_scoring=False verifies pure cosine."""
        retriever = MemoryRetriever(memory_dir=self.memory_dir)
        query = _unit_vec(0)  # closest to delta_executor.py
        results = retriever.top_k(query, k=3, source_types=["file"], use_weighted_scoring=False)
        self.assertEqual(len(results), 3)
        # First result must be delta_executor.py (cosine score = 1.0)
        self.assertEqual(results[0].file_path, "scripts/delta_executor.py")
        self.assertAlmostEqual(results[0].score, 1.0, places=6)
        # Scores must be in descending order
        scores = [r.score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_weighted_scoring_composite_formula(self):
        """
        Weighted scoring must produce a composite score matching:
          0.6 * semantic + 0.2 * recency + 0.1 * exec_success + 0.1 * arch_relevance

        At bootstrap with no execution_log or decision_log:
          recency = 0.5 (neutral prior, hash not a timestamp)
          exec_success = 0.5 (neutral prior, no history)
          arch_relevance = 0.0 (no decision_log entries)

        For the best-matching record (cosine=1.0):
          expected = 0.6*1.0 + 0.2*0.5 + 0.1*0.5 + 0.1*0.0 = 0.75
        """
        retriever = MemoryRetriever(memory_dir=self.memory_dir)
        query = _unit_vec(0)  # cosine = 1.0 against delta_executor.py
        results = retriever.top_k(query, k=1, source_types=["file"], use_weighted_scoring=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_path, "scripts/delta_executor.py")
        expected_composite = 0.6 * 1.0 + 0.2 * 0.5 + 0.1 * 0.5 + 0.1 * 0.0
        self.assertAlmostEqual(results[0].score, expected_composite, places=5)
        # Score metadata must expose component breakdowns
        meta = results[0].metadata
        self.assertIn("semantic", meta)
        self.assertIn("recency", meta)
        self.assertIn("exec_success", meta)
        self.assertIn("arch_relevance", meta)

    def test_filter_by_file_type_python(self):
        """file_type='python' must exclude non-.py results."""
        retriever = MemoryRetriever(memory_dir=self.memory_dir)
        query = _unit_vec(2)  # closest to main.tf
        results = retriever.top_k(query, k=10, file_type="python", source_types=["file"])
        paths = [r.file_path for r in results]
        for p in paths:
            self.assertTrue(
                p.endswith(".py"),
                f"Non-Python result slipped through filter: {p}"
            )

    def test_filter_by_module_prefix(self):
        """module='scripts/' must restrict results to the scripts directory."""
        retriever = MemoryRetriever(memory_dir=self.memory_dir)
        query = _unit_vec(0)
        results = retriever.top_k(query, k=10, module="scripts/", source_types=["file"])
        for r in results:
            self.assertTrue(
                r.file_path.startswith("scripts/"),
                f"Result outside module filter: {r.file_path}"
            )

    def test_top_k_respects_k_limit(self):
        """top_k(k=1) must return at most 1 result."""
        retriever = MemoryRetriever(memory_dir=self.memory_dir)
        results = retriever.top_k(_unit_vec(0), k=1, source_types=["file"])
        self.assertLessEqual(len(results), 1)

    def test_empty_corpus_returns_empty_list(self):
        """Retrieval against an empty corpus must return an empty list without error."""
        empty_dir = os.path.join(self.memory_dir, "empty_sub")
        os.makedirs(os.path.join(empty_dir, "embeddings"), exist_ok=True)
        _write_embeddings(empty_dir, "file_embeddings.json", [])
        retriever = MemoryRetriever(memory_dir=empty_dir)
        results = retriever.top_k(_unit_vec(0), k=10, source_types=["file"])
        self.assertEqual(results, [])

    def test_missing_embedding_file_returns_empty_gracefully(self):
        """Retriever must not raise when an embedding file is absent."""
        retriever = MemoryRetriever(memory_dir=self.memory_dir)
        # "issue" corpus doesn't exist in this tmpdir
        results = retriever.top_k(_unit_vec(0), k=5, source_types=["issue"])
        self.assertEqual(results, [])

    def test_retrieval_result_to_dict_serialisable(self):
        """RetrievalResult.to_dict() must produce JSON-serialisable dicts."""
        r = RetrievalResult(
            file_path="scripts/gh_utils.py",
            score=0.95,
            chunk_index=0,
            total_chunks=1,
            source_type="file",
        )
        d = r.to_dict()
        # Must round-trip through JSON without error
        serialised = json.dumps(d)
        parsed = json.loads(serialised)
        self.assertEqual(parsed["file_path"], "scripts/gh_utils.py")
        self.assertAlmostEqual(parsed["score"], 0.95, places=4)


if __name__ == "__main__":
    unittest.main()
