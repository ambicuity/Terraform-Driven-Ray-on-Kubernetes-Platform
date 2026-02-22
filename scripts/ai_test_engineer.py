#!/usr/bin/env python3
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
import time
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
PR_NUMBER = os.environ.get("PR_NUMBER", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GEMINI_MODEL = "gemini-3-flash-preview"
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


def github_api(url: str, accept: str = "application/vnd.github.v3+json"):
    """Make an authenticated GitHub API request."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
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


def fetch_pr_diff() -> str:
    """Fetch the PR diff."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}"
    diff = github_api(url, "application/vnd.github.v3.diff")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n... [diff truncated] ..."
    return diff


def fetch_pr_metadata() -> dict:
    """Fetch PR metadata."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}"
    raw = github_api(url)
    return json.loads(raw) if raw else {}


def call_gemini(prompt: str) -> str:
    """Call Gemini API with retry."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    for attempt in range(4):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return "Gemini returned an empty response."
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code in (429, 500, 503) and attempt < 3:
                delay = [10, 30, 60][attempt]
                print(f"Gemini {e.code} — retry in {delay}s...", file=sys.stderr)
                time.sleep(delay)
                continue
            return f"⚠️ Gemini API error: {e.code}"

    return "⚠️ Gemini API failed after retries."


def post_comment(body: str) -> None:
    """Post the test suggestions as a PR comment."""
    comment = (
        "## 🧪 AI Test Engineer\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated test suggestions by Gemini AI. "
        "Review and adapt before committing.*"
    )
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{PR_NUMBER}/comments"
    req = urllib.request.Request(
        url,
        data=json.dumps({"body": comment}).encode("utf-8"),
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
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
    for var in ["GEMINI_API_KEY", "GITHUB_TOKEN", "PR_NUMBER", "GITHUB_REPOSITORY"]:
        if not os.environ.get(var):
            print(f"Missing: {var}", file=sys.stderr)
            sys.exit(1)

    print(f"Analyzing PR #{PR_NUMBER} for test opportunities...")

    diff = fetch_pr_diff()
    metadata = fetch_pr_metadata()
    title = metadata.get("title", "N/A")
    print(f"PR: {title} ({len(diff)} chars)")

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"PR Title: {title}\n"
        f"Changed Files: {metadata.get('changed_files', 'N/A')}\n\n"
        f"--- DIFF ---\n{diff}\n--- END DIFF ---"
    )

    print("Generating test suggestions...")
    result = call_gemini(prompt)
    print(f"Generated: {len(result)} chars")

    post_comment(result)


if __name__ == "__main__":
    main()
