#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
test_decision_extractor.py — Unit tests for decision_extractor.py.

Verifies tag extraction, secret scrubbing, deduplication,
ADR detection, and PR body decision parsing.
"""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from decision_extractor import (
    extract_inline_tags,
    extract_adr_files,
    extract_pr_decisions,
    deduplicate_decisions,
    _scrub_secrets,
    _decision_id,
)


class TestExtractInlineTags(unittest.TestCase):

    def _write_file(self, tmpdir: str, name: str, content: str) -> str:
        path = os.path.join(tmpdir, name)
        with open(path, "w") as fh:
            fh.write(content)
        return path

    def test_arch_decision_tag_extracted(self):
        """ARCH_DECISION: tag in a Python comment must be extracted."""
        content = (
            "# ARCH_DECISION: Using label-swap as distributed lock\n"
            "def claim_issue(): pass\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_file(tmpdir, "gh_utils.py", content)
            tags = extract_inline_tags(path, "scripts/gh_utils.py", tmpdir)
            self.assertEqual(len(tags), 1)
            self.assertEqual(tags[0]["type"], "ARCH_DECISION")
            self.assertIn("label-swap", tags[0]["context"])

    def test_security_boundary_tag_extracted(self):
        """SECURITY_BOUNDARY: tag must be extracted with correct type."""
        content = "# SECURITY_BOUNDARY: Agents cannot write to .github/workflows/\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_file(tmpdir, "gh_utils.py", content)
            tags = extract_inline_tags(path, "scripts/gh_utils.py", tmpdir)
            self.assertEqual(len(tags), 1)
            self.assertEqual(tags[0]["type"], "SECURITY_BOUNDARY")

    def test_performance_constraint_tag_extracted(self):
        """PERFORMANCE_CONSTRAINT: tag must be extracted."""
        content = "# PERFORMANCE_CONSTRAINT: Gemini Pro thinking budget capped at 8192 tokens\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_file(tmpdir, "gh_utils.py", content)
            tags = extract_inline_tags(path, "scripts/gh_utils.py", tmpdir)
            self.assertEqual(len(tags), 1)
            self.assertEqual(tags[0]["type"], "PERFORMANCE_CONSTRAINT")

    def test_multiple_tags_per_file(self):
        """Multiple tags in a single file must all be extracted."""
        content = (
            "# ARCH_DECISION: Use Gemini Flash for triage — lower cost\n"
            "# SECURITY_BOUNDARY: No secrets in environment except via os.environ\n"
            "def main(): pass\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_file(tmpdir, "config.py", content)
            tags = extract_inline_tags(path, "scripts/config.py", tmpdir)
            self.assertEqual(len(tags), 2)

    def test_no_tag_returns_empty(self):
        """A file with no decision tags must return an empty list."""
        content = "import os\n\ndef main():\n    pass\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_file(tmpdir, "clean.py", content)
            tags = extract_inline_tags(path, "scripts/clean.py", tmpdir)
            self.assertEqual(tags, [])

    def test_source_field_includes_line_number(self):
        """Extracted tags must include an approximate line number in 'source'."""
        content = "# line 1\n# line 2\n# ARCH_DECISION: something important\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_file(tmpdir, "agent.py", content)
            tags = extract_inline_tags(path, "scripts/agent.py", tmpdir)
            self.assertTrue(
                ":" in tags[0]["source"],
                f"Expected 'file:line' format in source, got: {tags[0]['source']}"
            )
            line_num = int(tags[0]["source"].split(":")[-1])
            self.assertGreaterEqual(line_num, 3)  # tag is on line 3


class TestScrubSecrets(unittest.TestCase):

    def test_long_alphanumeric_string_redacted(self):
        """32+ character alphanumeric strings must be redacted."""
        text = "Token: ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        result = _scrub_secrets(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123456789", result)

    def test_short_strings_preserved(self):
        """Normal short strings (under 32 chars) must not be redacted."""
        text = "Use label-swap as distributed lock"
        result = _scrub_secrets(text)
        self.assertEqual(result, text)

    def test_empty_string_safe(self):
        """Empty string must return empty string without error."""
        self.assertEqual(_scrub_secrets(""), "")


class TestDecisionId(unittest.TestCase):

    def test_deterministic_output(self):
        """Same inputs must always produce the same decision_id."""
        id1 = _decision_id("ARCH_DECISION", "scripts/gh_utils.py", 0)
        id2 = _decision_id("ARCH_DECISION", "scripts/gh_utils.py", 0)
        self.assertEqual(id1, id2)

    def test_different_inputs_produce_different_ids(self):
        """Different inputs must produce different decision_ids."""
        id1 = _decision_id("ARCH_DECISION", "scripts/gh_utils.py", 0)
        id2 = _decision_id("SECURITY_BOUNDARY", "scripts/gh_utils.py", 0)
        self.assertNotEqual(id1, id2)

    def test_prefix_reflects_type(self):
        """ARCH_DECISION must produce an ARCH- prefixed ID."""
        did = _decision_id("ARCH_DECISION", "foo.py", 0)
        self.assertTrue(did.startswith("ARCH-"), f"Bad prefix: {did}")


class TestExtractPRDecisions(unittest.TestCase):

    def test_arch_decision_in_pr_body(self):
        """ARCH_DECISION tag in PR body must be extracted as PR_DECISION."""
        pr_body = (
            "## PR: Implement label-swap lock\n\n"
            "# ARCH_DECISION: Label swap chosen over file-based lock for atomicity\n"
        )
        decisions = extract_pr_decisions(42, pr_body)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["pr_number"], 42)
        self.assertIn("label swap", decisions[0]["context"].lower())

    def test_no_tags_returns_empty(self):
        """PR body with no decision tags must return empty list."""
        pr_body = "Fixed a typo in the README."
        decisions = extract_pr_decisions(10, pr_body)
        self.assertEqual(decisions, [])


class TestDeduplicateDecisions(unittest.TestCase):

    def test_duplicate_ids_deduplicated(self):
        """Two records with the same decision_id must be collapsed to one."""
        decisions = [
            {"decision_id": "ARCH-001", "type": "ARCH_DECISION", "context": "old"},
            {"decision_id": "ARCH-001", "type": "ARCH_DECISION", "context": "new"},
        ]
        result = deduplicate_decisions(decisions)
        self.assertEqual(len(result), 1)
        # Last one wins (newest record preserved)
        self.assertEqual(result[0]["context"], "new")

    def test_unique_ids_all_preserved(self):
        """Records with unique decision_ids must all be preserved."""
        decisions = [
            {"decision_id": "ARCH-001", "type": "ARCH_DECISION", "context": "a"},
            {"decision_id": "SEC-002", "type": "SECURITY_BOUNDARY", "context": "b"},
        ]
        result = deduplicate_decisions(decisions)
        self.assertEqual(len(result), 2)

    def test_empty_list_safe(self):
        """Empty input must return empty list."""
        self.assertEqual(deduplicate_decisions([]), [])


class TestExtractADRFiles(unittest.TestCase):

    def test_adr_file_detected(self):
        """A file named adr-001.md must be extracted as an ADR decision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adr_path = os.path.join(tmpdir, "adr-001.md")
            with open(adr_path, "w") as fh:
                fh.write("# ADR-001: Use Terraform for Infrastructure Management\n\n"
                         "We decided to use Terraform because it is declarative and supports drift detection.\n")
            decisions = extract_adr_files(tmpdir)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["type"], "ADR")
            self.assertIn("Terraform", decisions[0]["context"])

    def test_non_adr_markdown_not_extracted(self):
        """README.md must not be extracted as an ADR."""
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = os.path.join(tmpdir, "README.md")
            with open(readme_path, "w") as fh:
                fh.write("# This repository...\nSome content.\n")
            decisions = extract_adr_files(tmpdir)
            self.assertEqual(decisions, [])


if __name__ == "__main__":
    unittest.main()
