#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
test_validate_memory.py — Unit tests for validate_memory.py CI gate.

Verifies that the validation gate correctly:
  - Passes valid, well-formed memory artifacts
  - Rejects missing required fields
  - Rejects files that exceed size limits
  - Detects stale embedding hashes
  - Rejects model version mismatches
  - Detects invalid JSON
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from memory_schemas import (
    SCHEMA_VERSION,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    EMBEDDING_DIM,
)
from validate_memory import (
    check_json_parseability,
    check_schema_validation,
    check_size_budgets,
    check_model_version_consistency,
    check_embedding_hash_consistency,
)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

def _sha256_str(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh)


def _valid_embedding_envelope(records: list) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "model_name": EMBEDDING_MODEL_NAME,
        "model_version": EMBEDDING_MODEL_VERSION,
        "generated_at": "2026-02-27T13:00:00Z",
        "embeddings": records,
    }


def _valid_embedding_record(file_path: str, content: str = "print('hello')") -> dict:
    return {
        "file_path": file_path,
        "hash": _sha256_str(content),
        "chunk_index": 0,
        "total_chunks": 1,
        "embedding": [0.01] * EMBEDDING_DIM,
    }


def _valid_repo_graph() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": "2026-02-27T13:00:00Z",
        "nodes": [
            {
                "path": "scripts/delta_executor.py",
                "type": "python",
                "size_bytes": 15681,
                "hash": "sha256:abc",
            }
        ],
        "edges": [],
        "metrics": {
            "total_files": 1,
            "python_files": 1,
            "terraform_files": 0,
        },
    }


# ---------------------------------------------------------------------------
# Tests: JSON parseability
# ---------------------------------------------------------------------------

class TestJsonParseability(unittest.TestCase):

    def test_valid_json_passes(self):
        """Valid JSON files must produce no errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_json(os.path.join(tmpdir, "repo_graph.json"), {"key": "value"})
            errors = check_json_parseability(tmpdir)
            self.assertEqual(errors, [])

    def test_invalid_json_fails(self):
        """A file with invalid JSON must produce an error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "broken.json")
            with open(path, "w") as fh:
                fh.write("{not valid json")
            errors = check_json_parseability(tmpdir)
            self.assertTrue(
                any("broken.json" in e for e in errors),
                f"Expected error about broken.json, got: {errors}"
            )


# ---------------------------------------------------------------------------
# Tests: Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation(unittest.TestCase):

    def test_valid_repo_graph_passes(self):
        """A fully valid repo_graph.json must pass schema validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_json(os.path.join(tmpdir, "repo_graph.json"), _valid_repo_graph())
            errors = check_schema_validation(tmpdir)
            schema_errors = [e for e in errors if "repo_graph" in e]
            self.assertEqual(schema_errors, [])

    def test_missing_nodes_field_fails(self):
        """repo_graph.json missing 'nodes' field must fail validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            broken = _valid_repo_graph()
            del broken["nodes"]
            _write_json(os.path.join(tmpdir, "repo_graph.json"), broken)
            errors = check_schema_validation(tmpdir)
            self.assertTrue(
                any("repo_graph" in e and "nodes" in e for e in errors),
                f"Expected nodes-related error, got: {errors}"
            )

    def test_wrong_schema_version_fails(self):
        """A schema_version != '1.0' must fail validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            broken = _valid_repo_graph()
            broken["schema_version"] = "2.0"
            _write_json(os.path.join(tmpdir, "repo_graph.json"), broken)
            errors = check_schema_validation(tmpdir)
            self.assertTrue(
                any("schema_version" in e for e in errors),
                f"Expected schema_version error, got: {errors}"
            )

    def test_valid_embedding_file_passes(self):
        """A valid file_embeddings.json must pass schema validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            records = [_valid_embedding_record("scripts/delta_executor.py")]
            _write_json(
                os.path.join(embed_dir, "file_embeddings.json"),
                _valid_embedding_envelope(records)
            )
            errors = check_schema_validation(tmpdir)
            embed_errors = [e for e in errors if "file_embeddings" in e]
            self.assertEqual(embed_errors, [])


# ---------------------------------------------------------------------------
# Tests: Size budgets
# ---------------------------------------------------------------------------

class TestSizeBudgets(unittest.TestCase):

    def test_small_files_pass(self):
        """Files well under the size limit must produce no errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a tiny embedding file (< 1 KB)
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            records = [_valid_embedding_record("scripts/delta_executor.py")]
            _write_json(
                os.path.join(embed_dir, "file_embeddings.json"),
                _valid_embedding_envelope(records)
            )
            errors = check_size_budgets(tmpdir)
            self.assertEqual(errors, [])

    def test_oversized_file_fails(self):
        """A file exceeding its per-file limit must produce an error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            # Write a stub that exceeds the decision_log.json limit (2 MB)
            big_path = os.path.join(tmpdir, "decision_log.json")
            # Write 3 MB of content
            with open(big_path, "w") as fh:
                fh.write("x" * (3 * 1024 * 1024))
            errors = check_size_budgets(tmpdir)
            self.assertTrue(
                any("decision_log" in e and "limit" in e for e in errors),
                f"Expected size limit error, got: {errors}"
            )


# ---------------------------------------------------------------------------
# Tests: Model version consistency
# ---------------------------------------------------------------------------

class TestModelVersionConsistency(unittest.TestCase):

    def test_correct_model_version_passes(self):
        """Embedding files with correct model metadata must pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            _write_json(
                os.path.join(embed_dir, "file_embeddings.json"),
                _valid_embedding_envelope([])
            )
            errors = check_model_version_consistency(tmpdir)
            self.assertEqual(errors, [])

    def test_wrong_model_name_fails(self):
        """An embedding file with wrong model_name must fail consistency check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            envelope = _valid_embedding_envelope([])
            envelope["model_name"] = "openai/text-embedding-ada-002"
            _write_json(os.path.join(embed_dir, "file_embeddings.json"), envelope)
            errors = check_model_version_consistency(tmpdir)
            self.assertTrue(
                any("model_name" in e for e in errors),
                f"Expected model_name error, got: {errors}"
            )


# ---------------------------------------------------------------------------
# Tests: Hash consistency
# ---------------------------------------------------------------------------

class TestHashConsistency(unittest.TestCase):

    def test_matching_hash_passes(self):
        """An embedding whose hash matches the current file content must pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a real repo file
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            content = "print('hello world')\n"
            file_path = os.path.join(scripts_dir, "fix_issue_99.py")
            with open(file_path, "w") as fh:
                fh.write(content)

            # Write embedding with matching hash
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            records = [_valid_embedding_record("scripts/fix_issue_99.py", content)]
            _write_json(
                os.path.join(embed_dir, "file_embeddings.json"),
                _valid_embedding_envelope(records)
            )
            errors = check_embedding_hash_consistency(tmpdir, tmpdir)
            self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_stale_hash_detected(self):
        """An embedding with a hash that doesn't match the file must be flagged as stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(scripts_dir)
            # Write original content
            original_content = "x = 1\n"
            file_path = os.path.join(scripts_dir, "fix_issue_100.py")
            with open(file_path, "w") as fh:
                fh.write(original_content)

            # Create embedding with hash of different content (simulating stale)
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            stale_record = _valid_embedding_record("scripts/fix_issue_100.py", "x = 99\n")  # wrong content
            _write_json(
                os.path.join(embed_dir, "file_embeddings.json"),
                _valid_embedding_envelope([stale_record])
            )
            errors = check_embedding_hash_consistency(tmpdir, tmpdir)
            self.assertTrue(
                any("stale" in e for e in errors),
                f"Expected stale hash error, got: {errors}"
            )

    def test_missing_file_detected_as_stale_key(self):
        """An embedding record for a deleted file must be flagged as a stale key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            embed_dir = os.path.join(tmpdir, "embeddings")
            os.makedirs(embed_dir)
            # Embedding references a file that doesn't exist
            records = [_valid_embedding_record("scripts/deleted_script.py")]
            _write_json(
                os.path.join(embed_dir, "file_embeddings.json"),
                _valid_embedding_envelope(records)
            )
            errors = check_embedding_hash_consistency(tmpdir, tmpdir)
            self.assertTrue(
                any("stale key" in e for e in errors),
                f"Expected stale-key error, got: {errors}"
            )


if __name__ == "__main__":
    unittest.main()
