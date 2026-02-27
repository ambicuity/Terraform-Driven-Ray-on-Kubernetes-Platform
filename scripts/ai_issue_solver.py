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



SYSTEM_PROMPT = """\
# Role
You are the automated issue analyst for a production Terraform/EKS/Ray repository.
This repository deploys GPU-enabled Ray ML clusters on AWS EKS and consists of:

  Core infrastructure:
    terraform/main.tf          — EKS cluster, IAM, KMS, VPC
    terraform/node_pools.tf    — Node groups (CPU, GPU Spot, system)
    terraform/variables.tf     — All input variables with validation
    terraform/outputs.tf       — All module outputs
  Workload orchestration:
    helm/ray/values.yaml       — KubeRay RayCluster config (head + worker pods)
    helm/ray/templates/        — Kubernetes manifests for the Ray cluster
  Policy-as-code:
    policies/deny.rego         — OPA blocking rules (egress, public S3, no-IMDSv2)
    policies/warn.rego         — OPA advisory rules
  Automation agents:
    scripts/gamma_triage.py    — Triage agent (Gemini-powered)
    scripts/delta_executor.py  — Contributor agent (code generation)
    scripts/beta_reviewer.py   — Code review agent
    scripts/alpha_governor.py  — Governance agent (CHANGELOG, tags)
    scripts/gh_utils.py        — Shared GitHub + Gemini client library
  CI/CD:
    .github/workflows/         — 39 GitHub Actions workflows
  Tests:
    tests/                     — Python unittest suites

# Task
Analyse the issue and produce a structured solution plan.

# Output Format (follow exactly)
### 🔍 Root Cause Analysis
State the specific component (exact file name) that is affected. Describe the failure
mode or missing behaviour in one precise paragraph. Do NOT say "there may be an issue
with" — state what IS wrong based on what the issue describes.

### 📋 Implementation Plan
Numbered steps. Each step must name the exact file to edit and the specific function,
resource block, or policy rule to change. No step should say "update the configuration"
without specifying which key/block/line.

### 📁 Files to Modify
Bullet list of exact relative file paths (e.g., `terraform/node_pools.tf`,
`helm/ray/values.yaml`). Do not list files not in the repository tree.

### ⚠️ Risk Assessment
- **Complexity**: Low / Medium / High — with one-sentence justification
- **Breaking Changes**: Yes / No — state which Terraform outputs or Kubernetes APIs change
- **Estimated Effort**: <N> hours — be specific, not a range

### 🧪 Testing Strategy
Describe the exact test command(s) to verify the fix:
  - Python: `python -m pytest tests/test_<module>.py -v`
  - Terraform: `terraform validate && terraform plan -target=<resource>`
  - OPA: `opa test policies/ -v`
  - E2E: Which GitHub Actions workflow to trigger and what the expected result is.
"""


def github_api(url: str, token: str, accept: str = "application/vnd.github.v3+json") -> dict:
    """Make an authenticated GitHub API request."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
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


def fetch_issue(repo: str, issue_num: str, token: str) -> dict:
    """Fetch the issue details."""
    url = f"https://api.github.com/repos/{repo}/issues/{issue_num}"
    return github_api(url, token)


def fetch_repo_tree(repo: str, token: str) -> str:
    """Fetch the repository file tree for context."""
    url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
    data = github_api(url, token)
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


def post_comment(body: str, repo: str, issue_num: str, token: str) -> None:
    """Post the solution plan as an issue comment."""
    import urllib.request
    import urllib.error
    comment_body = (
        "## 🤖 AI Solution Plan\n\n"
        f"{body}\n\n"
        "---\n"
        "*Automated analysis powered by Gemini AI. "
        "This is a suggested approach — engineering review is recommended "
        "before implementation.*"
    )

    url = f"https://api.github.com/repos/{repo}/issues/{issue_num}/comments"
    payload = json.dumps({"body": comment_body}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {token}",
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
    from gh_utils import require_env, GeminiClient, GEMINI_MODEL_FLASH

    env = require_env("GEMINI_API_KEY", "GITHUB_TOKEN", "ISSUE_NUMBER", "GITHUB_REPOSITORY")
    api_key = env["GEMINI_API_KEY"]
    token = env["GITHUB_TOKEN"]
    issue_num = env["ISSUE_NUMBER"]
    repo = env["GITHUB_REPOSITORY"]

    print(f"Analyzing issue #{issue_num} in {repo}...")

    # Fetch context
    issue = fetch_issue(repo, issue_num, token)
    print(f"Issue: {issue.get('title', 'N/A')}")

    repo_tree = fetch_repo_tree(repo, token)
    print(f"Fetched repo tree: {len(repo_tree)} characters")

    # Call Gemini
    print("Sending to Gemini for analysis...")
    issue_context = (
        f"Issue Title: {issue.get('title', 'N/A')}\n"
        f"Issue Author: {issue.get('user', {}).get('login', 'N/A')}\n"
        f"Labels: {', '.join(l['name'] for l in issue.get('labels', []))}\n"
        f"\nIssue Body:\n{issue.get('body', 'No description provided.')}\n"
        f"\n--- REPOSITORY FILE TREE ---\n{repo_tree}\n--- END FILE TREE ---"
    )
    prompt = f"{SYSTEM_PROMPT}\n\n{issue_context}"
    
    gemini = GeminiClient(api_key, model=GEMINI_MODEL_FLASH)
    plan = gemini.generate(prompt)
    if not plan:
        plan = "⚠️ Gemini API failed to generate a response (e.g., due to rate limits or safety blocks)."
    print(f"Received plan: {len(plan)} characters")

    # Post the comment
    post_comment(plan, repo, issue_num, token)


if __name__ == "__main__":
    main()
