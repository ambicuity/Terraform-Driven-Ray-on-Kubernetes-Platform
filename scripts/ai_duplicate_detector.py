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
    "You are operating as a Senior Principal Engineer with 20+ years of experience "
    "in distributed systems and infrastructure.\n"
    "You are analyzing GitHub issues for a production-grade Terraform EKS + Ray ML "
    "infrastructure project.\n\n"
    "Given a NEW issue and a list of EXISTING open issues, apply structured reasoning "
    "to determine if the new issue is a duplicate or closely related to any existing issue.\n\n"
    "Rules:\n"
    "1. Maintain clear boundary control. Only flag duplicates if they are genuinely "
    "about the SAME problem or feature request.\n"
    "2. \"Related\" issues that discuss the same component but different aspects are NOT duplicates.\n"
    "3. Be conservative, evidence-based, and precise — false positives are worse than false negatives.\n\n"
    "If you find duplicates, respond in this exact format without hype language or generic praise:\n\n"
    "### \U0001f50d Potential Duplicate(s) Found\n\n"
    "| Existing Issue | Similarity | Reason |\n"
    "|---|---|---|\n"
    "| #<number> — <title> | High/Medium | Brief, technical explanation |\n\n"
    "> **Recommendation:** Consider closing this as a duplicate of #<number>, "
    "or merging the discussions.\n\n"
    "If NO duplicates are found, respond with exactly:\n"
    "**\u2705 No duplicate issues detected.** This issue appears to be unique."
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
