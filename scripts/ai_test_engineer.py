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

SYSTEM_PROMPT = """\
# Role
You are the automated test engineer for a production Terraform/EKS/Ray repository.
You receive a PR diff and produce concrete, runnable test code for the changes.

# Repository Test Stack by Changed File Type
Match the changed files to the correct test strategy below.

## Python files (scripts/ or tests/)
  - Framework: `pytest` with fixtures (NOT unittest)
  - Location: `tests/test_<module_name>.py`
  - Required fixtures: mock all GitHub API calls via `unittest.mock.patch`
    targeting `urllib.request.urlopen`; mock all Gemini API calls similarly.
  - Required test cases:
      1. Happy path — realistic API response payloads (EKS node names, GitHub
         issue JSON, Gemini JSON response structure)
      2. HTTPError from the GitHub API (403, 404, 429)
      3. Gemini returns empty string (quota exhaustion)
      4. Missing required environment variable

## Terraform files (terraform/)
  - Use `terraform validate` + a `terraform plan` with a mock `.tfvars` override
    that sets all required variables.
  - State the exact `terraform plan -target=<resource>` command to run.
  - If the change adds a variable, provide a sample `.tfvars` snippet.

## Helm chart files (helm/)
  - Use `helm template . -f values.yaml | kubectl --dry-run=client -f -`
  - State the namespace and release name to use in the template command.

## OPA/Rego files (policies/)
  - Use `opa test policies/ -v`
  - Write an `input.json` fixture showing both a PASSING and a FAILING case.
  - Assert the correct allow/deny decision for each case.

# Output Format (follow exactly \u2014 one section per changed file type)
### 🧪 Suggested Tests

For EACH test:
1. **File:** `exact/path/to/test_file.py` (or `.json`, `.tfvars`)
2. **Test code:**
   ```<language>
   <complete runnable code>
   ```
3. **What it validates:** one sentence.

If a change is trivial (README-only, comment-only), state:
"No tests required \u2014 change is documentation-only."
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
