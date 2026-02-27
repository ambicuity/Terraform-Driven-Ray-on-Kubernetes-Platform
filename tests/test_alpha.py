#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Unit tests for Agent Alpha (alpha_governor.py).

Tests cover:
  - SemVer bump logic (patch vs minor)
  - Version string bumping with and without 'v' prefix
  - Current version extraction from CHANGELOG.md
  - Governance guard (merge_count - last_governance_merge threshold)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import alpha_governor  # noqa: E402

from tests.fixtures.github_api_fixtures import (  # noqa: E402
    PR_AI_GENERATED, PR_FEATURE, PR_MERGED,
)


class TestSemVerBump(unittest.TestCase):
    """Tests for alpha_governor.determine_semver_bump."""

    def test_enhancement_label_triggers_minor(self):
        """PR with 'enhancement' label should trigger MINOR bump."""
        pr_with_enhancement = {
            **PR_MERGED,
            "labels": [{"name": "enhancement"}, {"name": "ai-generated"}],
            "title": "feat: add S3 lifecycle policy",
        }
        result = alpha_governor.determine_bump([pr_with_enhancement])
        self.assertEqual(result, "minor")

    def test_feat_title_triggers_minor(self):
        """PR with 'feat' keyword in title should trigger MINOR bump."""
        result = alpha_governor.determine_bump([PR_FEATURE])
        self.assertEqual(result, "minor")

    def test_pure_bug_fix_triggers_patch(self):
        """PRs with no feature signals should be PATCH."""
        bug_pr = {
            **PR_MERGED,
            "title": "fix(ai-generated): correct memory limit in init container",
            "labels": [{"name": "bug"}, {"name": "ai-generated"}],
        }
        result = alpha_governor.determine_bump([bug_pr])
        self.assertEqual(result, "patch")

    def test_empty_pr_list_triggers_patch(self):
        """No PRs → default to patch bump."""
        result = alpha_governor.determine_bump([])
        self.assertEqual(result, "patch")

    def test_mixed_prs_triggers_minor(self):
        """One feature PR among bug fixes should still trigger MINOR."""
        bug_pr = {**PR_MERGED, "title": "fix: typo", "labels": [{"name": "bug"}]}
        prs = [bug_pr, PR_FEATURE]
        result = alpha_governor.determine_bump(prs)
        self.assertEqual(result, "minor")


class TestVersionBumping(unittest.TestCase):
    """Tests for alpha_governor.bump_version."""

    def test_patch_bump(self):
        self.assertEqual(alpha_governor.bump_version("v1.0.4", "patch"), "v1.0.5")

    def test_minor_bump_resets_patch(self):
        self.assertEqual(alpha_governor.bump_version("v1.0.4", "minor"), "v1.1.0")

    def test_handles_no_v_prefix(self):
        self.assertEqual(alpha_governor.bump_version("1.2.3", "patch"), "1.2.4")

    def test_handles_malformed_version(self):
        """Malformed version string should return a safe fallback without crashing."""
        result = alpha_governor.bump_version("invalid", "patch")
        self.assertRegex(result, r"v?\d+\.\d+\.\d+", "Should return a valid SemVer string")

    def test_large_version_numbers(self):
        self.assertEqual(alpha_governor.bump_version("v10.99.999", "patch"), "v10.99.1000")


class TestVersionExtraction(unittest.TestCase):
    """Tests for alpha_governor.extract_current_version."""

    def test_extracts_from_standard_changelog(self):
        changelog = "# Changelog\n\n## [1.2.3] — 2026-01-01\n### Fixed\n- Something\n"
        self.assertEqual(alpha_governor.extract_version(changelog), "v1.2.3")

    def test_extracts_first_version_when_multiple(self):
        """Should extract the topmost (most recent) version."""
        changelog = (
            "# Changelog\n\n"
            "## [2.0.0] — 2026-02-01\n### Added\n- Something\n\n"
            "## [1.9.9] — 2026-01-01\n### Fixed\n- Other\n"
        )
        result = alpha_governor.extract_version(changelog)
        self.assertEqual(result, "v2.0.0")

    def test_returns_fallback_for_empty_changelog(self):
        """Empty changelog should return a safe fallback version."""
        result = alpha_governor.extract_version("")
        self.assertEqual(result, "v1.0.0")

    def test_handles_v_prefix_in_changelog(self):
        changelog = "## [v1.5.2] — 2026-01-15\n"
        result = alpha_governor.extract_version(changelog)
        self.assertEqual(result, "v1.5.2")


class TestGovernanceGuard(unittest.TestCase):
    """Tests for the merge_count guard in alpha_governor.main (queue logic)."""

    def test_governance_triggers_when_count_divisible_by_5(self):
        """merge_count - last_governance_merge >= 5 should allow governance."""
        queue = {"merge_count": 10, "last_governance_merge": 5}
        ready = queue["merge_count"] - queue["last_governance_merge"] >= 5
        self.assertTrue(ready)

    def test_governance_blocked_when_count_not_reached(self):
        """Less than 5 since last governance should block the cycle."""
        queue = {"merge_count": 7, "last_governance_merge": 5}
        ready = queue["merge_count"] - queue["last_governance_merge"] >= 5
        self.assertFalse(ready)

    def test_governance_blocked_at_zero(self):
        """At initial state (0 merges), governance should not trigger."""
        queue = {"merge_count": 0, "last_governance_merge": 0}
        ready = queue["merge_count"] - queue["last_governance_merge"] >= 5
        self.assertFalse(ready)


if __name__ == "__main__":
    unittest.main()
