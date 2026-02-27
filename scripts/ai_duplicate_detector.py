#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Gemini AI Duplicate Issue Detector.

When a new issue is created, fetches all open issues and asks Gemini
to determine if the new issue is a duplicate. Posts a comment linking
to potential duplicates.

Environment variables required:
  - GEMINI_API_KEY, GITHUB_TOKEN, ISSUE_NUMBER, GITHUB_REPOSITORY
"""

import os
import sys
import json
import time
# Legacy duplicate detector — now uses gh_utils.GeminiClient


SYSTEM_PROMPT = (
    "# Role\n"
    "You are the duplicate-detection agent for a production Terraform/EKS/Ray repository.\n"
    "This repository deploys GPU-enabled Ray ML clusters on AWS EKS using Terraform,\n"
    "KubeRay, Helm, and OPA (Open Policy Agent).\n\n"
    "# Task\n"
    "Determine whether the NEW ISSUE is a duplicate of any EXISTING OPEN ISSUE.\n\n"
    "# Duplicate Criteria (apply all three rules)\n"
    "An existing issue is a duplicate of the new issue ONLY IF:\n"
    "  1. Both issues describe the same failure mode OR the same feature request.\n"
    "     'Same failure mode' means the same component (e.g., EKS autoscaler, KubeRay\n"
    "     operator, OPA deny policy) fails in the same way (e.g., OOM, misconfiguration,\n"
    "     API error). Different symptoms in the same component are NOT duplicates.\n"
    "  2. Both issues describe the same affected component. An issue about\n"
    "     `helm/ray/values.yaml` and one about `terraform/node_pools.tf` are never\n"
    "     duplicates even if they both describe 'workers crashing'.\n"
    "  3. Your confidence that they describe the same root cause is HIGH (>80%).\n"
    "     If uncertain, do NOT flag as duplicate.\n\n"
    "# Anti-patterns (these are NOT duplicates)\n"
    "  - Two issues that mention the same AWS service but describe different failures.\n"
    "  - A bug report and a feature request for the same component.\n"
    "  - Two issues with similar titles but describing different error messages.\n\n"
    "# Output Format (STRICT \u2014 follow exactly)\n\n"
    "If duplicates found:\n"
    "### \U0001f50d Potential Duplicate(s) Found\n\n"
    "| Existing Issue | Similarity | Affected Component | Reason |\n"
    "|---|---|---|---|\n"
    "| #<number> \u2014 <title> | High | <exact file or subsystem> | "
    "<one sentence: same failure mode because...> |\n\n"
    "> **Recommendation:** Consider closing this as a duplicate of #<number>, "
    "or merging the discussions if they cover complementary aspects.\n\n"
    "If NO duplicates found:\n"
    "**\u2705 No duplicate issues detected.** This issue appears to be unique.\n"
    "Reason: <one sentence explaining what distinguishes it from the closest existing issue>."
)


def github_api(url: str, token: str) -> dict:
    """Make a GitHub API request."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "gemini-duplicate-detector",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.code}", file=sys.stderr)
        return {}


def fetch_all_issues(repo: str, issue_num: str, token: str) -> list:
    """Fetch all open issues (excluding the new one)."""
    issues: list[dict] = []
    page = 1
    while page <= 5:  # Cap at 5 pages (500 issues)
        url = (
            f"https://api.github.com/repos/{repo}/issues"
            f"?state=open&per_page=100&page={page}"
        )
        data = github_api(url, token)
        if not data or not isinstance(data, list):
            break
        for issue in data:
            # Skip PRs (GitHub API returns PRs as issues too)
            if "pull_request" in issue:
                continue
            if str(issue["number"]) != issue_num:
                issues.append({
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": (issue.get("body") or "")[:500],  # Truncate body
                    "labels": [label["name"] for label in issue.get("labels", [])],
                })
        if len(data) < 100:
            break
        page += 1
    return issues




def post_comment(body: str, issue_number: str, repo: str, token: str) -> None:
    """Post the duplicate analysis as an issue comment."""
    import urllib.request
    import urllib.error
    comment = (
        "## 🔍 Duplicate Issue Scan\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated scan by Gemini AI Duplicate Detector.*"
    )
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    req = urllib.request.Request(
        url,
        data=json.dumps({"body": comment}).encode("utf-8"),
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "gemini-duplicate-detector",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                print("✅ Duplicate scan posted.")
    except urllib.error.HTTPError as e:
        print(f"Error posting: {e.code}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    from gh_utils import require_env, GeminiClient, GEMINI_MODEL_FLASH

    env = require_env("GEMINI_API_KEY", "GITHUB_TOKEN", "ISSUE_NUMBER", "GITHUB_REPOSITORY")
    issue_number = env["ISSUE_NUMBER"]
    github_repository = env["GITHUB_REPOSITORY"]
    github_token = env["GITHUB_TOKEN"]

    print(f"Scanning for duplicates of issue #{issue_number}...")

    # Fetch the new issue
    new_issue = github_api(
        f"https://api.github.com/repos/{github_repository}/issues/{issue_number}",
        github_token,
    )
    if not new_issue:
        print("Failed to fetch new issue.", file=sys.stderr)
        sys.exit(1)

    # Fetch existing issues
    existing = fetch_all_issues(github_repository, issue_number, github_token)
    print(f"Found {len(existing)} existing open issues to compare against.")

    if not existing:
        print("No existing issues to compare. Skipping.")
        return

    # Build prompt
    existing_str = "\n".join(
        f"- #{i['number']}: {i['title']} [{', '.join(i['labels'])}]\n  {i['body'][:200]}"
        for i in existing
    )

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"--- NEW ISSUE ---\n"
        f"#{new_issue['number']}: {new_issue['title']}\n"
        f"Labels: {', '.join(l['name'] for l in new_issue.get('labels', []))}\n"
        f"Body:\n{(new_issue.get('body') or 'No description')[:1000]}\n"
        f"--- END NEW ISSUE ---\n\n"
        f"--- EXISTING OPEN ISSUES ---\n{existing_str}\n--- END ---"
    )

    print("Sending to Gemini for analysis...")
    gemini = GeminiClient(env["GEMINI_API_KEY"], model=GEMINI_MODEL_FLASH)
    result = gemini.generate(prompt)
    if not result:
        result = "⚠️ Gemini API failed to generate a response (e.g., due to rate limits or safety blocks)."
    print(f"Result: {len(result)} chars")

    post_comment(result, issue_number, github_repository, github_token)


if __name__ == "__main__":
    main()
