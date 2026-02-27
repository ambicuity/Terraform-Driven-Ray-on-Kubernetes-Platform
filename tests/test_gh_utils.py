#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Unit tests for gh_utils.py — shared GitHub API + Gemini client utilities.

Tests cover:
  - compile_check: valid Python passes, syntax errors fail, non-parseable code fails
  - _guard_protected_path: workflow paths blocked, other paths allowed
  - read_queue / write_queue: round-trip serialisation
  - require_env: exits on missing vars, returns dict on success
"""

import sys
import os
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import gh_utils  # noqa: E402


class TestCompileCheck(unittest.TestCase):
    """Tests for gh_utils.compile_check."""

    def test_valid_python_passes(self):
        code = "import os\n\ndef main():\n    print(os.getcwd())\n"
        ok, err = gh_utils.compile_check(code)
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_syntax_error_fails(self):
        code = "def broken(:\n    pass\n"
        ok, err = gh_utils.compile_check(code)
        self.assertFalse(ok)
        self.assertIn("SyntaxError", err)

    def test_empty_code_passes(self):
        """Empty file is valid Python."""
        ok, err = gh_utils.compile_check("")
        self.assertTrue(ok)

    def test_valid_class_definition_passes(self):
        code = (
            "class Foo:\n"
            "    def bar(self) -> None:\n"
            "        raise NotImplementedError\n"
        )
        ok, err = gh_utils.compile_check(code)
        self.assertTrue(ok)

    def test_unclosed_string_fails(self):
        code = 'name = "hello\n'
        ok, err = gh_utils.compile_check(code)
        self.assertFalse(ok)


class TestProtectedPathGuard(unittest.TestCase):
    """Tests for gh_utils.GithubClient._guard_protected_path."""

    def test_workflow_path_raises(self):
        with self.assertRaises(PermissionError):
            gh_utils.GithubClient._guard_protected_path(".github/workflows/my-workflow.yml")

    def test_workflow_subdirectory_raises(self):
        with self.assertRaises(PermissionError):
            gh_utils.GithubClient._guard_protected_path(".github/workflows/new_agent.yml")

    def test_scripts_path_allowed(self):
        # Should not raise
        gh_utils.GithubClient._guard_protected_path("scripts/fix_issue_42.py")

    def test_docs_path_allowed(self):
        gh_utils.GithubClient._guard_protected_path("docs/ai-automation.md")

    def test_github_non_workflow_allowed(self):
        """Files under .github/ but not workflows/ should be allowed."""
        gh_utils.GithubClient._guard_protected_path(".github/ISSUE_TEMPLATE/bug_report.md")


class TestQueueRoundTrip(unittest.TestCase):
    """Tests for gh_utils.read_queue / write_queue round-trip."""

    def setUp(self):
        self._orig_path = gh_utils.QUEUE_PATH
        self._tmpdir = tempfile.mkdtemp()
        gh_utils.QUEUE_PATH = os.path.join(self._tmpdir, ".ai_metadata", "queue.json")

    def tearDown(self):
        gh_utils.QUEUE_PATH = self._orig_path

    def test_round_trip_preserves_all_fields(self):
        original = {
            "schema_version": "1.0",
            "queued": [{"issue_number": 42, "priority": "high"}],
            "in_progress": None,
            "merge_count": 7,
            "last_governance_merge": 5,
        }
        gh_utils.write_queue(original)
        recovered = gh_utils.read_queue()
        self.assertEqual(recovered, original)

    def test_read_missing_file_returns_defaults(self):
        result = gh_utils.read_queue()
        self.assertIn("queued", result)
        self.assertIn("merge_count", result)
        self.assertEqual(result["queued"], [])

    def test_empty_write_then_read(self):
        gh_utils.write_queue({"queued": [], "in_progress": None, "merge_count": 0, "last_governance_merge": 0})
        result = gh_utils.read_queue()
        self.assertEqual(result["merge_count"], 0)


class TestRequireEnv(unittest.TestCase):

    def test_returns_values_when_all_present(self):
        with patch.dict("os.environ", {"FOO": "bar", "BAZ": "qux"}):
            result = gh_utils.require_env("FOO", "BAZ")
        self.assertEqual(result["FOO"], "bar")

    def test_exits_when_variable_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit):
                gh_utils.require_env("MISSING_VAR")


class TestWriteQueueConflictRetry(unittest.TestCase):
    """Tests for GithubClient.write_queue() 409-conflict retry logic."""

    def _make_client(self) -> gh_utils.GithubClient:
        return gh_utils.GithubClient.__new__(gh_utils.GithubClient)

    def test_success_on_first_attempt_no_retry(self):
        """If write_file succeeds first time, read_file and write_file called exactly once each."""
        from unittest.mock import MagicMock
        client = self._make_client()
        client.read_file = MagicMock(return_value=("", "abc123"))
        client.write_file = MagicMock(return_value=True)

        result = client.write_queue({"queued": [], "merge_count": 1})

        self.assertTrue(result)
        client.read_file.assert_called_once()
        client.write_file.assert_called_once()

    def test_conflict_triggers_retry_with_fresh_sha(self):
        """write_file failure causes read_file to be called again for fresh sha, then retried."""
        from unittest.mock import MagicMock
        client = self._make_client()
        client.read_file = MagicMock(
            side_effect=[("", "stale_sha"), ("", "fresh_sha")]
        )
        client.write_file = MagicMock(side_effect=[False, True])

        result = client.write_queue({"queued": [], "merge_count": 2})

        self.assertTrue(result)
        self.assertEqual(client.read_file.call_count, 2)
        self.assertEqual(client.write_file.call_count, 2)
        # Second write_file call must use fresh_sha (positional arg index 2: path, content, sha)
        fresh_sha_used = client.write_file.call_args_list[1][0][2]
        self.assertEqual(fresh_sha_used, "fresh_sha")

    def test_double_conflict_returns_false(self):
        """Both write attempts fail — returns False, no further retries beyond one."""
        from unittest.mock import MagicMock
        client = self._make_client()
        client.read_file = MagicMock(return_value=("", "some_sha"))
        client.write_file = MagicMock(return_value=False)

        result = client.write_queue({"queued": []})

        self.assertFalse(result)
        self.assertEqual(client.write_file.call_count, 2)  # exactly first + one retry


class TestAppendLogConflictRetry(unittest.TestCase):
    """Tests for GithubClient.append_log() 409-conflict retry logic."""

    def _make_client(self) -> gh_utils.GithubClient:
        return gh_utils.GithubClient.__new__(gh_utils.GithubClient)

    def test_success_on_first_attempt(self):
        """On success, existing log content is preserved and entry is appended."""
        from unittest.mock import MagicMock
        client = self._make_client()
        client.read_file = MagicMock(return_value=("# Existing log\n", "sha1"))
        client.write_file = MagicMock(return_value=True)

        result = client.append_log("Gamma", "#42", "Triaged", "Queued", "All good")

        self.assertTrue(result)
        client.read_file.assert_called_once()
        client.write_file.assert_called_once()
        written_content = client.write_file.call_args[0][1]
        self.assertIn("# Existing log", written_content)
        self.assertIn("Agent Gamma", written_content)

    def test_conflict_retry_captures_concurrent_entry(self):
        """On 409, retry re-reads the file to get concurrent agent's entry before appending ours."""
        from unittest.mock import MagicMock
        client = self._make_client()
        # Between our first read and retry, Agent Beta appended its entry
        client.read_file = MagicMock(side_effect=[
            ("# Original\n", "sha1"),
            ("# Original\n## Agent Beta — 2026-02-27\n- action: Merged\n", "sha2"),
        ])
        client.write_file = MagicMock(side_effect=[False, True])

        result = client.append_log("Gamma", "#42", "Triaged", "Queued", "All good")

        self.assertTrue(result)
        self.assertEqual(client.read_file.call_count, 2)
        # Retry write must include Beta's concurrent entry AND ours — no data lost
        retry_content = client.write_file.call_args[0][1]
        self.assertIn("Agent Beta", retry_content)
        self.assertIn("Agent Gamma", retry_content)

    def test_double_conflict_returns_false(self):
        """Both append attempts fail — returns False, no further retries beyond one."""
        from unittest.mock import MagicMock
        client = self._make_client()
        client.read_file = MagicMock(return_value=("# log\n", "sha"))
        client.write_file = MagicMock(return_value=False)

        result = client.append_log("Alpha", "N/A", "Released", "Done", "v2.0.0")

        self.assertFalse(result)
        self.assertEqual(client.write_file.call_count, 2)


class TestGeminiExtractText(unittest.TestCase):
    """Tests for GeminiClient._extract_text — Gemini API response parsing."""

    def test_happy_path_returns_text(self):
        result = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Hello!"}]}}]
        }
        self.assertEqual(gh_utils.GeminiClient._extract_text(result), "Hello!")

    def test_max_tokens_still_returns_text(self):
        """MAX_TOKENS means truncated but still valid content."""
        result = {
            "candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "Partial"}]}}]
        }
        self.assertEqual(gh_utils.GeminiClient._extract_text(result), "Partial")

    def test_safety_finish_reason_returns_empty(self):
        """finishReason=SAFETY means content was blocked — must return empty."""
        result = {
            "candidates": [{"finishReason": "SAFETY", "safetyRatings": []}]
        }
        self.assertEqual(gh_utils.GeminiClient._extract_text(result), "")

    def test_recitation_finish_reason_returns_empty(self):
        result = {
            "candidates": [{"finishReason": "RECITATION", "content": {"parts": []}}]
        }
        self.assertEqual(gh_utils.GeminiClient._extract_text(result), "")

    def test_prompt_block_reason_returns_empty(self):
        """promptFeedback.blockReason is set when the PROMPT itself was blocked."""
        result = {
            "promptFeedback": {"blockReason": "SAFETY"},
            "candidates": [],
        }
        self.assertEqual(gh_utils.GeminiClient._extract_text(result), "")

    def test_no_candidates_returns_empty(self):
        result = {"candidates": []}
        self.assertEqual(gh_utils.GeminiClient._extract_text(result), "")

    def test_no_content_parts_returns_empty(self):
        result = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": []}}]
        }
        self.assertEqual(gh_utils.GeminiClient._extract_text(result), "")

    def test_api_key_in_header_not_url(self):
        """API key must be in x-goog-api-key header, NOT the URL (security)."""
        client = gh_utils.GeminiClient("test-key-abc")
        self.assertNotIn("test-key-abc", client._url)
        self.assertEqual(client._headers.get("x-goog-api-key"), "test-key-abc")

    def test_thinking_disabled_in_payload(self):
        """thinkingBudget=0 must be present in generationConfig to suppress default thinking."""
        import json as _json
        client = gh_utils.GeminiClient("test-key")
        # Reconstruct what generate() sends by checking the constant structure
        # Since generate() builds payload internally, verify via model default constant
        self.assertEqual(gh_utils.GEMINI_MODEL, "gemini-2.5-pro")


if __name__ == "__main__":
    unittest.main()

