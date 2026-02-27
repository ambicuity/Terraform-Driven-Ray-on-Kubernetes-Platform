#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Unit tests for Agent Beta (beta_reviewer.py) — post-refactor.

Tests cover:
  - Hallucinated import detection from diff text
  - Technical Brief retrieval from queue.json state
  - Approval/rejection decision logic (mocked GithubClient + GeminiClient)
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import beta_reviewer  # noqa: E402

from tests.fixtures.github_api_fixtures import (  # noqa: E402
    DIFF_CLEAN, DIFF_WITH_HALLUCINATION, PR_AI_GENERATED,
)

MOCK_ENV = {
    "GEMINI_API_KEY": "test-key",
    "GITHUB_TOKEN": "test-token",
    "PR_NUMBER": "100",
    "GITHUB_REPOSITORY": "ambicuity/test-repo",
}


class TestHallucinatedImportDetection(unittest.TestCase):

    def test_clean_diff_returns_empty(self):
        self.assertEqual(beta_reviewer.detect_hallucinated_imports(DIFF_CLEAN), [])

    def test_diff_with_third_party_libraries_flagged(self):
        result = beta_reviewer.detect_hallucinated_imports(DIFF_WITH_HALLUCINATION)
        self.assertIn("requests", result)
        self.assertIn("boto3", result)
        self.assertIn("numpy", result)

    def test_removed_lines_not_flagged(self):
        diff = "--- a/old.py\n+++ b/new.py\n-import requests\n+import os\n"
        self.assertEqual(beta_reviewer.detect_hallucinated_imports(diff), [])

    def test_context_lines_not_flagged(self):
        diff = " import requests  # context line\n+import os\n"
        self.assertNotIn("requests", beta_reviewer.detect_hallucinated_imports(diff))

    def test_empty_diff(self):
        self.assertEqual(beta_reviewer.detect_hallucinated_imports(""), [])


class TestBriefRetrieval(unittest.TestCase):

    def test_from_in_progress(self):
        q = {"queued": [], "in_progress": {"pr_number": 100, "brief": "Fix OOM."}}
        self.assertEqual(beta_reviewer.get_brief(q, 100), "Fix OOM.")

    def test_from_queued_list(self):
        q = {"queued": [{"pr_number": 200, "brief": "Fix S3."}], "in_progress": None}
        self.assertEqual(beta_reviewer.get_brief(q, 200), "Fix S3.")

    def test_default_when_no_match(self):
        q = {"queued": [], "in_progress": None}
        self.assertIn("No Technical Brief", beta_reviewer.get_brief(q, 999))


class TestApprovalDecisionLogic(unittest.TestCase):
    """Integration tests for main() with mocked GithubClient and GeminiClient."""

    def _make_mocks(self, gemini_response: str, diff: str = DIFF_CLEAN, queue: dict | None = None):
        """Build fully mocked gh + gemini for a main() invocation."""
        if queue is None:
            queue = {"queued": [], "in_progress": None, "merge_count": 0, "last_governance_merge": 0}
        gh = MagicMock()
        gh.get_pr_diff.return_value = diff
        gh.get_pr.return_value = PR_AI_GENERATED
        gh.merge_pr.return_value = True
        gh.read_queue.return_value = queue
        gh.write_queue.return_value = True
        gh.append_log.return_value = True

        gemini = MagicMock()
        gemini.generate.return_value = gemini_response

        return gh, gemini

    def test_gemini_approved_calls_merge(self):
        queue = {"queued": [], "in_progress": {"pr_number": 100, "brief": "Fix OOM."},
                 "merge_count": 0, "last_governance_merge": 0}
        gh, gemini = self._make_mocks("APPROVED\nCode is production-safe.", queue=queue)

        with patch.dict("os.environ", MOCK_ENV), \
             patch("beta_reviewer.GithubClient", return_value=gh), \
             patch("beta_reviewer.GeminiClient", return_value=gemini):
            beta_reviewer.main()

        gh.merge_pr.assert_called_once_with(100)
        gh.post_comment.assert_called_once()

    def test_gemini_rejected_skips_merge(self):
        gh, gemini = self._make_mocks("REJECTED\n- No docstring\n- Missing error handling")

        with patch.dict("os.environ", MOCK_ENV), \
             patch("beta_reviewer.GithubClient", return_value=gh), \
             patch("beta_reviewer.GeminiClient", return_value=gemini):
            beta_reviewer.main()

        gh.merge_pr.assert_not_called()

    def test_hallucinated_imports_bypass_gemini(self):
        """Diff with hallucinated imports should reject without calling Gemini."""
        gh, gemini = self._make_mocks("APPROVED\n...", diff=DIFF_WITH_HALLUCINATION)

        with patch.dict("os.environ", MOCK_ENV), \
             patch("beta_reviewer.GithubClient", return_value=gh), \
             patch("beta_reviewer.GeminiClient", return_value=gemini):
            beta_reviewer.main()

        gemini.generate.assert_not_called()
        gh.merge_pr.assert_not_called()

    def test_governance_triggered_at_5th_merge(self):
        """merge_count reaching a multiple of 5 should trigger governance dispatch."""
        queue = {"queued": [], "in_progress": {"pr_number": 100, "brief": "x"},
                 "merge_count": 4, "last_governance_merge": 0}
        gh, gemini = self._make_mocks("APPROVED\nCode clean.", queue=queue)

        with patch.dict("os.environ", MOCK_ENV), \
             patch("beta_reviewer.GithubClient", return_value=gh), \
             patch("beta_reviewer.GeminiClient", return_value=gemini):
            beta_reviewer.main()

        gh.trigger_dispatch.assert_called_once_with("governance-cycle")


if __name__ == "__main__":
    unittest.main()
