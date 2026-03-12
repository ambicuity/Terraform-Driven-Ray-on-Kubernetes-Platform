"""Tests for scripts/drift_detector.py."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import drift_detector


def write_plan(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_parse_plan_returns_empty_string_when_no_drift(tmp_path: Path) -> None:
    plan_path = write_plan(
        tmp_path,
        {
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.logs",
                    "type": "aws_s3_bucket",
                    "change": {"actions": ["no-op"]},
                }
            ]
        },
    )

    assert drift_detector.parse_plan(str(plan_path)) == ""


def test_parse_plan_formats_drifted_resources(tmp_path: Path) -> None:
    plan_path = write_plan(
        tmp_path,
        {
            "resource_changes": [
                {
                    "address": "aws_eks_cluster.main",
                    "type": "aws_eks_cluster",
                    "change": {"actions": ["update"]},
                },
                {
                    "address": "aws_iam_role.node",
                    "type": "aws_iam_role",
                    "change": {"actions": ["delete", "create"]},
                },
            ]
        },
    )

    report = drift_detector.parse_plan(str(plan_path))

    assert "Infrastructure Drift Detected" in report
    assert "`aws_eks_cluster.main`" in report
    assert "`UPDATE`" in report
    assert "`DELETE, CREATE`" in report


def test_parse_plan_handles_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    report = drift_detector.parse_plan(str(missing_path))

    assert report.startswith("Error reading plan file:")
