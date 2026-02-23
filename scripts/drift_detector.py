#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Infrastructure Drift Detector — Automated Day 2 Observability.

This script:
1. Parses a Terraform plan JSON file
2. Identifies resources with drift
3. Creates a GitHub Issue with a structured drift report
"""

import os
import sys
import json
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")


def post_github_issue(title: str, body: str) -> None:
    """Create a new GitHub issue with the drift report."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues"
    payload = json.dumps({
        "title": title,
        "body": body,
        "labels": ["infrastructure-drift", "ops"]
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "drift-detector",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                print("✅ Drift issue created successfully.")
            else:
                print(f"⚠️ Unexpected response: {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"Error creating issue: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)


def parse_plan(plan_file: str) -> str:
    """Parse the JSON plan and return a markdown-formatted report."""
    try:
        with open(plan_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        return f"Error reading plan file: {str(e)}"

    resource_changes = data.get("resource_changes", [])
    drifted_resources = []

    for change in resource_changes:
        actions = change.get("change", {}).get("actions", [])
        if "no-op" not in actions and actions:
            drifted_resources.append({
                "address": change["address"],
                "actions": actions,
                "type": change["type"]
            })

    if not drifted_resources:
        return ""

    report = "## 🔍 Infrastructure Drift Detected\n\n"
    report += "The automated drift detection scan has identified discrepancies between the live AWS environment and the Terraform state.\n\n"
    report += "### Summary of Changes\n\n"
    report += "| Resource Address | Change Type | Resource Type |\n"
    report += "|------------------|-------------|---------------|\n"

    for dr in drifted_resources:
        action_str = ", ".join(dr["actions"]).upper()
        report += f"| `{dr['address']}` | `{action_str}` | `{dr['type']}` |\n"

    report += "\n---\n"
    report += "### Next Steps\n"
    report += "1. Review the changes above.\n"
    report += "2. Run `terraform plan` locally to inspect the full diff.\n"
    report += "3. Run `terraform apply` to reconcile the state, or update the code if the change was intentional.\n\n"
    report += "*Automated report by Infrastructure Drift Detector.*"

    return report


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: drift_detector.py <plan_json_file>")
        sys.exit(1)

    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("Missing GITHUB_TOKEN or GITHUB_REPOSITORY environment variables.")
        sys.exit(1)

    plan_file = sys.argv[1]
    report = parse_plan(plan_file)

    if report:
        title = "⚠️ Infrastructure Drift Detected: Ray ML Cluster"
        post_github_issue(title, report)
        print("Drift detected and reported.")
    else:
        print("No drift detected.")


if __name__ == "__main__":
    main()
