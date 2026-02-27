#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Gemini AI Issue Solver — Automated issue analysis and solution planning.

When a new issue is created, this script:
1. Fetches the issue title and body
2. Fetches the repository file tree for context
3. Sends everything to Gemini with a tailored prompt
4. Posts a structured solution plan as a comment

Environment variables required:
  - GEMINI_API_KEY: Google Gemini API key
  - GITHUB_TOKEN: GitHub token (auto-provided by Actions)
  - ISSUE_NUMBER: Issue number
  - GITHUB_REPOSITORY: owner/repo (auto-provided by Actions)
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GEMINI_MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = """You are a Senior Principal Engineer working on a production-grade Terraform module
that deploys Ray ML clusters on AWS EKS. A new issue has been filed in the repository.

Your deep expertise covers:
- Terraform / HCL module design, variables, outputs, and state management
- AWS EKS, VPC, IAM, KMS, CloudWatch, and node group configuration
- Kubernetes, Helm, KubeRay operator, and autoscaling
- OPA/Rego policy authoring for infrastructure governance
- Python (Ray, NumPy) for ML workloads
- GitHub Actions CI/CD pipelines

Analyze the issue and provide a **structured solution plan** in this exact format:

### 🔍 Root Cause Analysis
Explain what is likely causing the issue or what the request entails.

### 📋 Implementation Plan
A numbered step-by-step plan with specific files and functions to modify.

### 📁 Files to Modify
A bullet list of exact file paths that would need changes.

### ⚠️ Risk Assessment
- **Complexity**: Low / Medium / High
- **Breaking Changes**: Yes / No
- **Estimated Effort**: Hours / Days

### 🧪 Testing Strategy
How to verify the fix/feature works correctly.

Be specific, actionable, and production-minded. Reference actual file paths from the repository
when possible. Do NOT pad with generic advice — focus on the concrete implementation.
"""


def github_api(url: str, accept: str = "application/vnd.github.v3+json") -> dict:
    """Make an authenticated GitHub API request."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": accept,
            "User-Agent": "gemini-issue-solver",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e.code} {e.reason}", file=sys.stderr)
        return {}


def fetch_issue() -> dict:
    """Fetch the issue details."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{ISSUE_NUMBER}"
    return github_api(url)


def fetch_repo_tree() -> str:
    """Fetch the repository file tree for context."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/git/trees/main?recursive=1"
    data = github_api(url)
    if not data:
        return "Unable to fetch repository tree."

    tree = data.get("tree", [])
    # Filter to relevant files only
    relevant_extensions = {
        ".tf", ".tfvars", ".py", ".rego", ".yml", ".yaml",
        ".md", ".json", ".hcl"
    }
    paths = []
    for item in tree:
        if item["type"] == "blob":
            path = item["path"]
            ext = os.path.splitext(path)[1].lower()
            if ext in relevant_extensions or path in {"Makefile", "Dockerfile"}:
                paths.append(path)

    return "\n".join(sorted(paths))


def call_gemini(issue: dict, repo_tree: str) -> str:
    """Send the issue to Gemini and get a solution plan."""
    issue_context = (
        f"Issue Title: {issue.get('title', 'N/A')}\n"
        f"Issue Author: {issue.get('user', {}).get('login', 'N/A')}\n"
        f"Labels: {', '.join(l['name'] for l in issue.get('labels', []))}\n"
        f"\nIssue Body:\n{issue.get('body', 'No description provided.')}\n"
        f"\n--- REPOSITORY FILE TREE ---\n{repo_tree}\n--- END FILE TREE ---"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + "\n\n" + issue_context}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
        },
    }

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    max_retries = 3
    backoff_delays = [10, 30, 60]

    for attempt in range(max_retries + 1):
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
                        return parts[0].get("text", "No response generated.")
                return "Gemini returned an empty response."
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code in (429, 500, 503) and attempt < max_retries:
                delay = backoff_delays[attempt]
                print(
                    f"Gemini API {e.code} — retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                continue
            print(f"Gemini API error: {e.code} — {body}", file=sys.stderr)
            return f"⚠️ Gemini API returned an error: {e.code}"

    return "⚠️ Gemini API failed after all retries."


def post_comment(body: str) -> None:
    """Post the solution plan as an issue comment."""
    comment_body = (
        "## 🤖 AI Solution Plan\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated analysis powered by Gemini AI. "
        "This is a suggested approach — engineering review is recommended "
        "before implementation.*"
    )

    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{ISSUE_NUMBER}/comments"
    payload = json.dumps({"body": comment_body}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "gemini-issue-solver",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                print("✅ Solution plan posted successfully.")
            else:
                print(f"⚠️ Unexpected response: {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"Error posting comment: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if not ISSUE_NUMBER:
        missing.append("ISSUE_NUMBER")
    if not GITHUB_REPOSITORY:
        missing.append("GITHUB_REPOSITORY")

    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing issue #{ISSUE_NUMBER} in {GITHUB_REPOSITORY}...")

    # Fetch context
    issue = fetch_issue()
    print(f"Issue: {issue.get('title', 'N/A')}")

    repo_tree = fetch_repo_tree()
    print(f"Fetched repo tree: {len(repo_tree)} characters")

    # Call Gemini
    print("Sending to Gemini for analysis...")
    plan = call_gemini(issue, repo_tree)
    print(f"Received plan: {len(plan)} characters")

    # Post the comment
    post_comment(plan)


if __name__ == "__main__":
    main()
