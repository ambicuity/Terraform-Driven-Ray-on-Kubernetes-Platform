#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Gemini AI PR Reviewer — CodeRabbit-style automated code review.

This script:
1. Fetches the PR diff from the GitHub API
2. Sends it to the Gemini API with a tailored system prompt
3. Posts the AI's review as a PR comment

Environment variables required:
  - GEMINI_API_KEY: Google Gemini API key
  - GITHUB_TOKEN: GitHub token (auto-provided by Actions)
  - PR_NUMBER: Pull request number
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
PR_NUMBER = os.environ.get("PR_NUMBER", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GEMINI_MODEL = "gemini-2.0-flash"
MAX_DIFF_CHARS = 60000  # Truncate very large diffs to stay within token limits

SYSTEM_PROMPT = (
    "You are operating as a Senior Principal Engineer with 20+ years of experience "
    "in software engineering, distributed systems, system architecture, DevOps, and "
    "production-grade delivery.\n"
    "You are performing a code review on a Pull Request for a production-grade "
    "Terraform module that deploys Ray ML clusters on AWS EKS.\n\n"
    "Your core operating principles:\n"
    "- Extreme ownership, structured reasoning, and architectural discipline.\n"
    "- Production-safe engineering standards.\n"
    "- Risk awareness and clear boundary control.\n"
    "- Your tone must be professional, authoritative, collaborative, and engineering-focused.\n\n"
    "Do NOT:\n"
    "- Use hype language, dramatic formatting, or generic praise.\n"
    "- Perform unsolicited architectural audits unless the PR explicitly changes architecture.\n"
    "- Speculate about scalability issues without evidence.\n"
    "- Suggest \"fix in next commit\" workarounds.\n\n"
    "Review the following PR diff and provide:\n\n"
    "### 1. Problem Understanding\n"
    "- Summarize what this PR accomplishes concisely.\n\n"
    "### 2. Technical Analysis\n"
    "- Note any security concerns (exposed secrets, overly permissive IAM, missing encryption).\n"
    "- Note any Terraform, Kubernetes, or Python anti-patterns.\n"
    "- Verify production safety (error handling, timeout handling, idempotency, etc.).\n\n"
    "### 3. Recommendation & Risk Assessment\n"
    "- Provide a clear Low / Medium / High risk rating with justification.\n"
    "- State the impact surface and rollback considerations if relevant.\n\n"
    "### 4. Implementation Suggestions (If Applicable)\n"
    "- Concrete, actionable improvements with code snippets where helpful.\n\n"
    "Format your response in clean GitHub-flavored Markdown. "
    "Be specific and constructive. Focus entirely on substance."
)


def fetch_pr_diff() -> str:
    """Fetch the PR diff from the GitHub API."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3.diff",
            "User-Agent": "gemini-ai-reviewer",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            diff = resp.read().decode("utf-8", errors="replace")
            if len(diff) > MAX_DIFF_CHARS:
                diff = diff[:MAX_DIFF_CHARS] + "\n\n... [diff truncated due to size] ..."
            return diff
    except urllib.error.HTTPError as e:
        print(f"Error fetching PR diff: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)


def fetch_pr_metadata() -> dict:
    """Fetch PR title, body, and file list."""
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/pulls/{PR_NUMBER}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "gemini-ai-reviewer",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Error fetching PR metadata: {e.code} {e.reason}", file=sys.stderr)
        return {}


def call_gemini(diff: str, metadata: dict) -> str:
    """Send the diff to Gemini and get a review, with retry on rate limits."""
    pr_context = (
        f"PR Title: {metadata.get('title', 'N/A')}\n"
        f"PR Author: {metadata.get('user', {}).get('login', 'N/A')}\n"
        f"Changed Files: {metadata.get('changed_files', 'N/A')}\n"
        f"Additions: +{metadata.get('additions', 0)} | "
        f"Deletions: -{metadata.get('deletions', 0)}\n"
        f"PR Description:\n{metadata.get('body', 'No description provided.')}\n"
    )

    user_prompt = f"{pr_context}\n\n--- DIFF START ---\n{diff}\n--- DIFF END ---"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_PROMPT + "\n\n" + user_prompt}
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
    backoff_delays = [10, 30, 60]  # seconds

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
            # Retry on rate limit (429) or server errors (500, 503)
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
    """Post the review as a PR comment."""
    comment_body = (
        "## 🤖 Gemini AI Review\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated review powered by Gemini AI. "
        "This is advisory — always apply engineering judgment.*"
    )

    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{PR_NUMBER}/comments"
    payload = json.dumps({"body": comment_body}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "gemini-ai-reviewer",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                print("✅ Review posted successfully.")
            else:
                print(f"⚠️ Unexpected response: {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"Error posting comment: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    # Validate required environment variables
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if not PR_NUMBER:
        missing.append("PR_NUMBER")
    if not GITHUB_REPOSITORY:
        missing.append("GITHUB_REPOSITORY")

    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    print(f"Reviewing PR #{PR_NUMBER} in {GITHUB_REPOSITORY}...")

    # Step 1: Fetch the diff
    diff = fetch_pr_diff()
    print(f"Fetched diff: {len(diff)} characters")

    # Step 2: Fetch PR metadata
    metadata = fetch_pr_metadata()
    print(f"PR: {metadata.get('title', 'N/A')}")

    # Step 3: Call Gemini
    print("Sending to Gemini for review...")
    review = call_gemini(diff, metadata)
    print(f"Received review: {len(review)} characters")

    # Step 4: Post the comment
    post_comment(review)


if __name__ == "__main__":
    main()
