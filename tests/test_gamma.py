#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Unit tests for Agent Gamma (gamma_triage.py) — post-refactor.

Tests cover:
  - Semantic duplicate detection (mocked Gemini returning JSON)
  - Marker validation
  - Priority assignment
"""

import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import gamma_triage  # noqa: E402

from tests.fixtures.github_api_fixtures import (  # noqa: E402
    ISSUE_VALID,
    ISSUE_MISSING_MARKERS,
    ISSUE_DUPLICATE_CANDIDATE,
    ISSUE_LOW_PRIORITY,
)


class TestSemanticDuplicateDetection(unittest.TestCase):
    """Tests for gamma_triage.detect_duplicates_semantic."""

    def _gemini(self, response: str) -> MagicMock:
        m = MagicMock()
        m.generate.return_value = response
        return m

    def test_detects_semantic_duplicate_from_gemini_response(self):
        """When Gemini returns a matching issue number, it is flagged as duplicate."""
        gemini = self._gemini(json.dumps([ISSUE_DUPLICATE_CANDIDATE["number"]]))
        result = gamma_triage.detect_duplicates_semantic(
            ISSUE_VALID, [ISSUE_DUPLICATE_CANDIDATE], gemini
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["number"], ISSUE_DUPLICATE_CANDIDATE["number"])

    def test_empty_gemini_response_returns_empty(self):
        """Empty Gemini response → no duplicates (fail safe)."""
        gemini = self._gemini("[]")
        result = gamma_triage.detect_duplicates_semantic(ISSUE_VALID, [ISSUE_DUPLICATE_CANDIDATE], gemini)
        self.assertEqual(result, [])

    def test_malformed_gemini_json_returns_empty(self):
        """Non-parseable Gemini response → no duplicates (safe fallback, no crash)."""
        gemini = self._gemini("I cannot determine duplicates.")
        result = gamma_triage.detect_duplicates_semantic(ISSUE_VALID, [ISSUE_DUPLICATE_CANDIDATE], gemini)
        self.assertEqual(result, [])

    def test_empty_closed_issues_skips_gemini(self):
        """With no closed issues, Gemini should not be called."""
        gemini = self._gemini("")
        result = gamma_triage.detect_duplicates_semantic(ISSUE_VALID, [], gemini)
        gemini.generate.assert_not_called()
        self.assertEqual(result, [])

    def test_self_is_excluded_from_candidates(self):
        """The same issue number as the new issue should not appear in closed candidates."""
        same_issue = {**ISSUE_VALID}  # number == 42
        gemini = self._gemini(json.dumps([42]))
        # Even if Gemini returns 42, it should be filtered out because number == ISSUE_VALID['number']
        result = gamma_triage.detect_duplicates_semantic(ISSUE_VALID, [same_issue], gemini)
        self.assertEqual(result, [])


class TestMarkerValidation(unittest.TestCase):
    """Tests for gamma_triage.validate_markers."""

    def test_all_markers_present(self):
        missing = gamma_triage.validate_markers(ISSUE_VALID["body"])
        self.assertEqual(missing, [])

    def test_all_markers_missing(self):
        missing = gamma_triage.validate_markers("gpu nodes broken please fix")
        self.assertEqual(set(missing), {"environment", "steps_to_reproduce", "expected_vs_actual"})

    def test_partial_markers(self):
        body = "Kubernetes cluster version 1.31 is installed."
        missing = gamma_triage.validate_markers(body)
        self.assertNotIn("environment", missing)
        self.assertIn("steps_to_reproduce", missing)
        self.assertIn("expected_vs_actual", missing)

    def test_empty_body_flags_all(self):
        self.assertEqual(len(gamma_triage.validate_markers("")), 3)

    def test_deterministic(self):
        body = ISSUE_VALID["body"]
        self.assertEqual(gamma_triage.validate_markers(body), gamma_triage.validate_markers(body))


class TestPriorityAssignment(unittest.TestCase):
    """Tests for gamma_triage.assign_priority."""

    def test_crash_triggers_high(self):
        issue = {**ISSUE_VALID, "title": "crash on cold start", "body": ""}
        self.assertEqual(gamma_triage.assign_priority(issue), "priority:high")

    def test_security_triggers_high(self):
        issue = {**ISSUE_VALID, "title": "security vulnerability in IAM", "body": ""}
        self.assertEqual(gamma_triage.assign_priority(issue), "priority:high")

    def test_typo_triggers_low(self):
        self.assertEqual(gamma_triage.assign_priority(ISSUE_LOW_PRIORITY), "priority:low")

    def test_neutral_triggers_medium(self):
        issue = {**ISSUE_VALID, "title": "node group does not start", "body": ""}
        self.assertEqual(gamma_triage.assign_priority(issue), "priority:medium")

    def test_high_wins_over_low(self):
        issue = {**ISSUE_VALID, "title": "crash typo in doc", "body": ""}
        self.assertEqual(gamma_triage.assign_priority(issue), "priority:high")


if __name__ == "__main__":
    unittest.main()
