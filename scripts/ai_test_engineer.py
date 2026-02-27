#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Gemini AI Test Engineer — Suggests unit tests for PR changes.

Analyzes the PR diff and generates test suggestions for:
- Python code → pytest test cases
- Terraform code → tftest.hcl validation rules
- OPA policies → conftest test cases

Environment variables required:
  - GEMINI_API_KEY, GITHUB_TOKEN, PR_NUMBER, GITHUB_REPOSITORY
"""

import os
import sys
import json

MAX_DIFF_CHARS = 50000

SYSTEM_PROMPT = """You are a Senior Test Engineer specializing in Infrastructure-as-Code and ML platform testing.

Analyze the PR diff and generate **concrete, ready-to-use test code** for the changes.

Rules:
- For Python changes → generate `pytest` test functions with proper fixtures
- For Terraform changes → generate `tftest.hcl` mock-based test blocks
- For OPA/Rego changes → generate `conftest` test data and expected results
- For Helm changes → generate `helm template` + kube-score validation steps

Format your response as:

### 🧪 Suggested Tests

For each test, provide:
1. File path where the test should live
2. Complete, runnable test code in a fenced code block
3. Brief explanation of what it validates

Be specific. Generate REAL test code, not pseudocode. Include edge cases.
If the changes are trivial (e.g., docs or CI config), say so and skip test generation.
"""


def github_api(url: str, token: str, accept: str = "application/vnd.github.v3+json"):
    """Make an authenticated GitHub API request."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": accept,
            "User-Agent": "gemini-test-engineer",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.code} {e.reason}", file=sys.stderr)
        return ""


def fetch_pr_diff(repo: str, pr_num: str, token: str) -> str:
    """Fetch the PR diff."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
    diff = github_api(url, token, "application/vnd.github.v3.diff")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n... [diff truncated] ..."
    return diff


def fetch_pr_metadata(repo: str, pr_num: str, token: str) -> dict:
    """Fetch PR metadata."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
    raw = github_api(url, token)
    return json.loads(raw) if raw else {}


def post_comment(body: str, repo: str, pr_num: str, token: str) -> None:
    """Post the test suggestions as a PR comment."""
    import urllib.request
    import urllib.error
    comment = (
        "## 🧪 AI Test Engineer\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated test suggestions by Gemini AI. "
        "Review and adapt before committing.*"
    )
    url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments"
    req = urllib.request.Request(
        url,
        data=json.dumps({"body": comment}).encode("utf-8"),
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "gemini-test-engineer",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                print("✅ Test suggestions posted.")
    except urllib.error.HTTPError as e:
        print(f"Error posting comment: {e.code}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    from gh_utils import require_env, GeminiClient, GEMINI_MODEL_PRO

    env = require_env("GEMINI_API_KEY", "GITHUB_TOKEN", "PR_NUMBER", "GITHUB_REPOSITORY")
    api_key = env["GEMINI_API_KEY"]
    token = env["GITHUB_TOKEN"]
    pr_num = env["PR_NUMBER"]
    repo = env["GITHUB_REPOSITORY"]

    print(f"Analyzing PR #{pr_num} for test opportunities...")

    diff = fetch_pr_diff(repo, pr_num, token)
    metadata = fetch_pr_metadata(repo, pr_num, token)
    title = metadata.get("title", "N/A")
    print(f"PR: {title} ({len(diff)} chars)")

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"PR Title: {title}\n"
        f"Changed Files: {metadata.get('changed_files', 'N/A')}\n\n"
        f"--- DIFF ---\n{diff}\n--- END DIFF ---"
    )

    print("Generating test suggestions...")
    gemini = GeminiClient(api_key, model=GEMINI_MODEL_PRO)
    result = gemini.generate(prompt)
    if not result:
        result = "⚠️ Gemini API failed to generate a response (e.g., due to rate limits or safety blocks)."
    print(f"Generated: {len(result)} chars")

    post_comment(result, repo, pr_num, token)


if __name__ == "__main__":
    main()
