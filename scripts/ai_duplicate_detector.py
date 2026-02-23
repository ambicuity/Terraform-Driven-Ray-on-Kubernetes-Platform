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
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GEMINI_MODEL = "gemini-3-flash-preview"

SYSTEM_PROMPT = """You are analyzing GitHub issues for a Terraform EKS + Ray ML infrastructure project.

Given a NEW issue and a list of EXISTING open issues, determine if the new issue is a duplicate
or closely related to any existing issue.

Rules:
1. Only flag duplicates if they are genuinely about the SAME problem or feature request.
2. "Related" issues that discuss the same component but different aspects are NOT duplicates.
3. Be conservative — false positives are worse than false negatives.

If you find duplicates, respond in this exact format:

### 🔍 Potential Duplicate(s) Found

| Existing Issue | Similarity | Reason |
|---|---|---|
| #<number> — <title> | High/Medium | Brief explanation |

> **Recommendation:** Consider closing this as a duplicate of #<number>, or merging the discussions.

If NO duplicates are found, respond with exactly:
**✅ No duplicate issues detected.** This issue appears to be unique.
"""


def github_api(url: str) -> dict:
    """Make a GitHub API request."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
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


def fetch_all_issues() -> list:
    """Fetch all open issues (excluding the new one)."""
    issues: list[dict] = []
    page = 1
    while page <= 5:  # Cap at 5 pages (500 issues)
        url = (
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues"
            f"?state=open&per_page=100&page={page}"
        )
        data = github_api(url)
        if not data or not isinstance(data, list):
            break
        for issue in data:
            # Skip PRs (GitHub API returns PRs as issues too)
            if "pull_request" in issue:
                continue
            if str(issue["number"]) != ISSUE_NUMBER:
                issues.append({
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": (issue.get("body") or "")[:500],  # Truncate body
                    "labels": [l["name"] for l in issue.get("labels", [])],
                })
        if len(data) < 100:
            break
        page += 1
    return issues


def call_gemini(prompt: str) -> str:
    """Call Gemini with retry."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
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
            e.read()
            if e.code in (429, 500, 503) and attempt < 3:
                delay = [10, 30, 60][attempt]
                print(f"Gemini {e.code} — retry in {delay}s...", file=sys.stderr)
                time.sleep(delay)
                continue
            return f"⚠️ Gemini API error: {e.code}"

    return "⚠️ Gemini API failed after retries."


def post_comment(body: str) -> None:
    """Post the duplicate analysis as an issue comment."""
    comment = (
        "## 🔍 Duplicate Issue Scan\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated scan by Gemini AI Duplicate Detector.*"
    )
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{ISSUE_NUMBER}/comments"
    req = urllib.request.Request(
        url,
        data=json.dumps({"body": comment}).encode("utf-8"),
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
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
    for var in ["GEMINI_API_KEY", "GITHUB_TOKEN", "ISSUE_NUMBER", "GITHUB_REPOSITORY"]:
        if not os.environ.get(var):
            print(f"Missing: {var}", file=sys.stderr)
            sys.exit(1)

    print(f"Scanning for duplicates of issue #{ISSUE_NUMBER}...")

    # Fetch the new issue
    new_issue = github_api(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{ISSUE_NUMBER}"
    )
    if not new_issue:
        print("Failed to fetch new issue.", file=sys.stderr)
        sys.exit(1)

    # Fetch existing issues
    existing = fetch_all_issues()
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
    result = call_gemini(prompt)
    print(f"Result: {len(result)} chars")

    post_comment(result)


if __name__ == "__main__":
    main()
