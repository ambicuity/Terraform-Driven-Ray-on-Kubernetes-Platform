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


def fetch_pr_diff(repo: str, pr_num: str, token: str) -> str:
    """Fetch the PR diff from the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
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


def fetch_pr_metadata(repo: str, pr_num: str, token: str) -> dict:
    """Fetch PR title, body, and file list."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
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



def post_comment(body: str, repo: str, pr_num: str, token: str) -> None:
    """Post the review as a PR comment."""
    comment_body = (
        "## 🤖 Gemini AI Review\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated review powered by Gemini AI. "
        "This is advisory — always apply engineering judgment.*"
    )

    url = f"https://api.github.com/repos/{repo}/issues/{pr_num}/comments"
    payload = json.dumps({"body": comment_body}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {token}",
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
    from gh_utils import require_env, GeminiClient, GEMINI_MODEL_PRO

    env = require_env("GEMINI_API_KEY", "GITHUB_TOKEN", "PR_NUMBER", "GITHUB_REPOSITORY")
    api_key = env["GEMINI_API_KEY"]
    token = env["GITHUB_TOKEN"]
    pr_num = env["PR_NUMBER"]
    repo = env["GITHUB_REPOSITORY"]

    print(f"Reviewing PR #{pr_num} in {repo}...")

    # Step 1: Fetch the diff
    diff = fetch_pr_diff(repo, pr_num, token)
    print(f"Fetched diff: {len(diff)} characters")

    # Step 2: Fetch PR metadata
    metadata = fetch_pr_metadata(repo, pr_num, token)
    print(f"PR: {metadata.get('title', 'N/A')}")

    # Step 3: Call Gemini
    print("Sending to Gemini for review...")
    pr_context = (
        f"PR Title: {metadata.get('title', 'N/A')}\n"
        f"PR Author: {metadata.get('user', {}).get('login', 'N/A')}\n"
        f"Changed Files: {metadata.get('changed_files', 'N/A')}\n"
        f"Additions: +{metadata.get('additions', 0)} | "
        f"Deletions: -{metadata.get('deletions', 0)}\n"
        f"PR Description:\n{metadata.get('body', 'No description provided.')}\n"
    )
    user_prompt = f"{pr_context}\n\n--- DIFF START ---\n{diff}\n--- DIFF END ---"
    prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    gemini = GeminiClient(api_key, model=GEMINI_MODEL_PRO)
    review = gemini.generate(prompt)
    if not review:
        review = "⚠️ Gemini API failed to generate a response (e.g., due to rate limits or safety blocks)."
    print(f"Received review: {len(review)} characters")

    # Step 4: Post the comment
    post_comment(review, repo, pr_num, token)


if __name__ == "__main__":
    main()
