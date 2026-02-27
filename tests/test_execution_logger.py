#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
test_execution_logger.py — Unit tests for execution_logger.py.

Tests ExecutionRecord validation, log_execution() append logic,
deduplication behavior, success weight computation, and recency decay.
"""

import json
import math
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from execution_logger import (
    ExecutionRecord,
    make_input_hash,
    make_run_id,
    log_execution,
    load_execution_history,
    compute_execution_success_weight,
    MAX_RUNS_IN_LOG,
)
from memory_retriever import _recency_weight, _parse_iso


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _valid_record(**kwargs) -> ExecutionRecord:
    defaults = dict(
        agent="Delta",
        trigger_event="issue_labeled",
        trigger_source="issue/42",
        input_hash=make_input_hash("test issue body"),
        retrieved_context_ids=["file:scripts/gh_utils.py", "decision:ARCH-001"],
        decision_summary="Applied label-swap lock; generated fix for missing import guard",
        actions_taken=["label_swap", "pr_opened"],
        outcome="success",
        ci_status="green",
        duration_ms=4321,
        confidence=0.88,
    )
    defaults.update(kwargs)
    return ExecutionRecord(**defaults)


# ---------------------------------------------------------------------------
# Tests: ExecutionRecord.validate()
# ---------------------------------------------------------------------------

class TestExecutionRecordValidation(unittest.TestCase):

    def test_valid_record_does_not_raise(self):
        record = _valid_record()
        record.validate()  # should not raise

    def test_invalid_agent_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _valid_record(agent="Epsilon").validate()
        self.assertIn("Invalid agent", str(ctx.exception))

    def test_invalid_outcome_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _valid_record(outcome="unknown").validate()
        self.assertIn("Invalid outcome", str(ctx.exception))

    def test_invalid_action_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _valid_record(actions_taken=["launch_missile"]).validate()
        self.assertIn("Invalid action", str(ctx.exception))

    def test_confidence_out_of_range_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _valid_record(confidence=1.5).validate()
        self.assertIn("confidence", str(ctx.exception))

    def test_input_hash_without_prefix_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _valid_record(input_hash="abc123").validate()
        self.assertIn("sha256:", str(ctx.exception))

    def test_decision_summary_too_long_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _valid_record(decision_summary="x" * 501).validate()
        self.assertIn("decision_summary", str(ctx.exception))

    def test_invalid_ci_status_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _valid_record(ci_status="yellow").validate()
        self.assertIn("ci_status", str(ctx.exception))


# ---------------------------------------------------------------------------
# Tests: make_input_hash
# ---------------------------------------------------------------------------

class TestMakeInputHash(unittest.TestCase):

    def test_deterministic(self):
        h1 = make_input_hash("same content")
        h2 = make_input_hash("same content")
        self.assertEqual(h1, h2)

    def test_sha256_prefix(self):
        h = make_input_hash("hello")
        self.assertTrue(h.startswith("sha256:"))

    def test_different_content_different_hash(self):
        h1 = make_input_hash("content a")
        h2 = make_input_hash("content b")
        self.assertNotEqual(h1, h2)

    def test_hash_length(self):
        h = make_input_hash("abc")
        # sha256: prefix + 64 hex chars
        self.assertEqual(len(h), 7 + 64)


# ---------------------------------------------------------------------------
# Tests: log_execution()
# ---------------------------------------------------------------------------

class TestLogExecution(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_creates_log_file_on_first_call(self):
        record = _valid_record()
        success = log_execution(record, repo_root=self.tmpdir.name)
        self.assertTrue(success)
        log_path = os.path.join(self.tmpdir.name, ".memory", "execution_log.json")
        self.assertTrue(os.path.isfile(log_path))

    def test_written_record_is_valid_json(self):
        log_execution(_valid_record(), repo_root=self.tmpdir.name)
        log_path = os.path.join(self.tmpdir.name, ".memory", "execution_log.json")
        with open(log_path) as fh:
            data = json.load(fh)
        self.assertIn("runs", data)
        self.assertEqual(len(data["runs"]), 1)

    def test_second_call_appends(self):
        log_execution(_valid_record(outcome="success"), repo_root=self.tmpdir.name)
        log_execution(_valid_record(outcome="failure", failure_reason="API 429"), repo_root=self.tmpdir.name)
        log_path = os.path.join(self.tmpdir.name, ".memory", "execution_log.json")
        with open(log_path) as fh:
            data = json.load(fh)
        self.assertEqual(len(data["runs"]), 2)

    def test_most_recent_first_ordering(self):
        """Runs must be prepended (most recent first)."""
        log_execution(_valid_record(decision_summary="first run"), repo_root=self.tmpdir.name)
        log_execution(_valid_record(decision_summary="second run"), repo_root=self.tmpdir.name)
        log_path = os.path.join(self.tmpdir.name, ".memory", "execution_log.json")
        with open(log_path) as fh:
            data = json.load(fh)
        self.assertEqual(data["runs"][0]["decision_summary"], "second run")

    def test_invalid_record_returns_false(self):
        bad = _valid_record(agent="NotAnAgent")
        result = log_execution(bad, repo_root=self.tmpdir.name)
        self.assertFalse(result)

    def test_run_cap_enforced(self):
        """After MAX_RUNS_IN_LOG records, log must not grow beyond cap."""
        # Write MAX_RUNS_IN_LOG + 3 records
        for i in range(MAX_RUNS_IN_LOG + 3):
            log_execution(
                _valid_record(decision_summary=f"run {i}"),
                repo_root=self.tmpdir.name,
            )
        log_path = os.path.join(self.tmpdir.name, ".memory", "execution_log.json")
        with open(log_path) as fh:
            data = json.load(fh)
        self.assertLessEqual(len(data["runs"]), MAX_RUNS_IN_LOG)


# ---------------------------------------------------------------------------
# Tests: compute_execution_success_weight
# ---------------------------------------------------------------------------

class TestComputeExecutionSuccessWeight(unittest.TestCase):

    def test_no_history_returns_neutral(self):
        """File with no execution history must return 0.5 (neutral prior)."""
        weight = compute_execution_success_weight("scripts/unknown.py", [])
        self.assertEqual(weight, 0.5)

    def test_all_successes_returns_one(self):
        history = [
            {"retrieved_context_ids": ["file:scripts/gh_utils.py"], "outcome": "success"},
            {"retrieved_context_ids": ["file:scripts/gh_utils.py"], "outcome": "success"},
        ]
        weight = compute_execution_success_weight("scripts/gh_utils.py", history)
        self.assertAlmostEqual(weight, 1.0, places=6)

    def test_all_failures_returns_zero(self):
        history = [
            {"retrieved_context_ids": ["file:scripts/gh_utils.py"], "outcome": "failure"},
        ]
        weight = compute_execution_success_weight("scripts/gh_utils.py", history)
        self.assertAlmostEqual(weight, 0.0, places=6)

    def test_mixed_outcomes_correct_ratio(self):
        history = [
            {"retrieved_context_ids": ["file:scripts/gh_utils.py"], "outcome": "success"},
            {"retrieved_context_ids": ["file:scripts/gh_utils.py"], "outcome": "failure"},
            {"retrieved_context_ids": ["file:scripts/gh_utils.py"], "outcome": "success"},
        ]
        weight = compute_execution_success_weight("scripts/gh_utils.py", history)
        self.assertAlmostEqual(weight, 2 / 3, places=6)

    def test_unrelated_file_not_counted(self):
        """Context IDs for other files must not affect the target file's weight."""
        history = [
            {"retrieved_context_ids": ["file:scripts/other.py"], "outcome": "failure"},
        ]
        weight = compute_execution_success_weight("scripts/gh_utils.py", history)
        self.assertEqual(weight, 0.5)  # neutral — not in any run


# ---------------------------------------------------------------------------
# Tests: _recency_weight
# ---------------------------------------------------------------------------

class TestRecencyWeight(unittest.TestCase):

    def test_neutral_for_hash_input(self):
        """Non-timestamp input (SHA-256 hash) must return neutral 0.5."""
        w = _recency_weight("sha256:abc123", "2026-02-27T13:00:00Z")
        self.assertEqual(w, 0.5)

    def test_recent_timestamp_near_one(self):
        """A timestamp from 1 hour ago must return a weight close to 1.0."""
        from datetime import datetime, timezone, timedelta
        now_dt = datetime(2026, 2, 27, 13, 0, 0, tzinfo=timezone.utc)
        one_hour_ago = (now_dt - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        w = _recency_weight(one_hour_ago, now_str)
        self.assertGreater(w, 0.99, f"Expected weight near 1.0 for 1h-old record, got {w}")

    def test_old_timestamp_near_zero(self):
        """A timestamp from 6 months ago must return low weight (< 0.1)."""
        from datetime import datetime, timezone, timedelta
        now_dt = datetime(2026, 2, 27, 13, 0, 0, tzinfo=timezone.utc)
        old = (now_dt - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        w = _recency_weight(old, now_str)
        self.assertLess(w, 0.1, f"Expected low weight for 180-day-old record, got {w}")

    def test_half_life_at_30_days(self):
        """Weight at exactly 30 days must be approximately 0.5."""
        from datetime import datetime, timezone, timedelta
        now_dt = datetime(2026, 2, 27, 13, 0, 0, tzinfo=timezone.utc)
        thirty_days_ago = (now_dt - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        w = _recency_weight(thirty_days_ago, now_str)
        self.assertAlmostEqual(w, 0.5, delta=0.005)


if __name__ == "__main__":
    unittest.main()
