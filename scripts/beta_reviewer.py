#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Agent Beta (Core Maintainer) — Phase 3 of the Autonomous AI Engineering Lifecycle.

The Gatekeeper. Triggered when a PR with 'ai-generated' label is opened/updated.

Review pipeline:
  1. Fetch the PR diff.
  2. Local import scan — fast, no API call, catches third-party hallucinations.
  3. Gemini deep review — logic integrity, PEP8, security, error handling.
  4. REJECT: post bulleted changes-requested + label; leaves 'status:in-progress' on
     the source issue so Delta can re-iterate.
  5. APPROVE: post approval comment, squash-merge via API, increment merge_count.
     If merge_count % 5 == 0 → fire 'governance-cycle' repository_dispatch for Alpha.

Environment variables required:
  GEMINI_API_KEY, GITHUB_TOKEN, PR_NUMBER, GITHUB_REPOSITORY
"""

import sys

from gh_utils import (
    GeminiClient,
    GithubClient,
    GEMINI_MODEL_FLASH,
    ALLOWED_IMPORTS,
    require_env,
)
import re

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# ALLOWED_IMPORTS imported from gh_utils — see that module for the authoritative list.

REVIEW_PROMPT = """\
# Role
You are Agent Beta, the Gatekeeper for a production Terraform/EKS/Ray repository that
deploys GPU-enabled Ray ML clusters on AWS EKS. You are the LAST automated gate before
AI-generated code is merged into `main`. Your review determines whether the code ships
or is sent back to Agent Delta for rework.

# What You Are Reviewing
This is a diff from an AI-generated pull request. The Technical Brief below describes
the exact problem the code was supposed to solve.

Technical Brief:
{brief}

# Review Checklist — Evaluate Each Point Explicitly
1. LOGIC INTEGRITY
   Does the code actually solve what the Technical Brief describes?
   Identify any missing cases, incorrect logic branches, or off-by-one errors.
   Flag if the fix addresses a symptom rather than the root cause.

2. SCOPE CREEP
   Does the diff modify files unrelated to the issue?
   Any change outside the scope of the Technical Brief is a blocker.

3. HALLUCINATED IMPORTS OR APIS
   Any import not in the stdlib allowlist (os, sys, re, json, time, datetime,
   subprocess, pathlib, urllib, http, io, base64, hashlib, threading, typing,
   unittest, collections, itertools, functools, math, logging, argparse, textwrap,
   shutil, tempfile, contextlib, dataclasses, abc, enum, copy, uuid, random,
   kubernetes, yaml) is a HARD REJECT — stop and reject immediately.
   Flag any call to a non-existent stdlib function (e.g., os.path.mkdirs).

4. SECURITY
   Hardcoded tokens, API keys, or AWS credentials → HARD REJECT.
   subprocess calls without shell=False → HARD REJECT.
   Unvalidated user input written to disk or executed.

5. ERROR HANDLING
   Every urllib.request.urlopen, subprocess.run, and open() call must be in a
   try/except block catching specific exception types.
   Bare `except:` or `except Exception: pass` → blocker.

6. PRODUCTION SAFETY
   No infinite loops without a timeout or counter guard.
   Network calls must have a timeout parameter.
   Temporary files must be cleaned up in a finally block.

7. PEP 8
   Lines over 120 characters, incorrect naming conventions (non-snake_case for
   functions/variables, non-PascalCase for classes). Flag concrete violations only.

# PR Diff ({max_chars} char limit)
{diff}

# Output Contract (STRICT — no deviation allowed)
If ALL 7 checklist items pass:
  Line 1: APPROVED
  Line 2: One sentence stating the specific reason the code is safe to merge.

If ANY item fails:
  Line 1: REJECTED
  Subsequent lines: One bullet per failure in this format:
    - [ChecklistItem] File:line_number or code construct — specific problem — required fix.

No preamble. No summary paragraph. No other text before or after.
"""

APPROVAL_COMMENT = """\
## ✅ Agent Beta — Code Review: APPROVED

{summary}

**Checklist:** PEP8 ✅ | Logic ✅ | Security ✅ | Imports ✅ | Error handling ✅

Merging to `main`.

---
*Agent Beta (Core Maintainer) · Gemini AI*
"""

REJECTION_COMMENT = """\
## ❌ Agent Beta — Changes Requested

{issues}

Agent Delta has been notified and will iterate.

---
*Agent Beta (Core Maintainer) · Gemini AI*
"""


# ---------------------------------------------------------------------------
# Local import hallucianstion scan
# ---------------------------------------------------------------------------

def detect_hallucinated_imports(diff: str) -> list[str]:
    """Scan only added lines (+) for imports not in the allowed stdlib set."""
    hallucinated: set[str] = set()
    for line in diff.splitlines():
        if not line.startswith("+"):
            continue
        m = re.match(r"^\+\s*import\s+([\w.]+)", line)
        if m:
            top = m.group(1).split(".")[0]
            if top not in ALLOWED_IMPORTS:
                hallucinated.add(top)
        m2 = re.match(r"^\+\s*from\s+([\w.]+)", line)
        if m2:
            top = m2.group(1).split(".")[0]
            if top not in ALLOWED_IMPORTS:
                hallucinated.add(top)
    return sorted(hallucinated)


def get_brief(queue: dict, pr_number: int) -> str:
    in_prog = queue.get("in_progress") or {}
    if in_prog.get("pr_number") == pr_number:
        return in_prog.get("brief", "No brief available.")
    for item in queue.get("queued", []):
        if item.get("pr_number") == pr_number:
            return item.get("brief", "No brief available.")
    return "No Technical Brief found for this PR."


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    env = require_env("GEMINI_API_KEY", "GITHUB_TOKEN", "PR_NUMBER", "GITHUB_REPOSITORY")
    gh = GithubClient(env["GITHUB_TOKEN"], env["GITHUB_REPOSITORY"])
    gemini = GeminiClient(env["GEMINI_API_KEY"], model=GEMINI_MODEL_FLASH)  # security review: reasoning quality critical
    pr_number = int(env["PR_NUMBER"])

    print(f"[Beta] Reviewing PR #{pr_number} in {env['GITHUB_REPOSITORY']}...")

    diff = gh.get_pr_diff(pr_number, max_chars=50_000)
    if not diff:
        print("[Beta] Empty diff. Aborting.", file=sys.stderr)
        sys.exit(1)

    metadata = gh.get_pr(pr_number)
    print(f"[Beta] PR: {metadata.get('title', 'N/A')}")

    queue = gh.read_queue()
    brief = get_brief(queue, pr_number)

    # --- Stage 1: Local import scan (fast, no API call) ---
    hallucinated = detect_hallucinated_imports(diff)
    if hallucinated:
        issues_md = "\n".join(f"- Hallucinated import: `{lib}`" for lib in hallucinated)
        gh.post_comment(pr_number, REJECTION_COMMENT.format(issues=issues_md))
        gh.ensure_label("changes-requested", "e11d48")
        gh.add_labels(pr_number, ["changes-requested"])
        gh.remove_label(pr_number, "needs-review")
        gh.append_log(
            "Beta", f"PR #{pr_number}",
            f"Rejected — hallucinated imports: {hallucinated}",
            "Changes Requested",
            "Delta should iterate"
        )
        print(f"[Beta] ❌ Rejected — hallucinated: {hallucinated}")
        return

    # --- Stage 2: Gemini deep review ---
    print("[Beta] Sending diff to Gemini for deep review...")
    response = gemini.generate(
        REVIEW_PROMPT.format(brief=brief, max_chars=50_000, diff=diff),
        temperature=0.1,
        max_tokens=2048
    )
    if not response:
        gh.append_log(
            "Beta", f"PR #{pr_number}",
            "Gemini API unreachable — aborting review (no mock approval)",
            "Review Failed",
            "Quota exhaustion or API error; a human reviewer must act."
        )
        print(
            "[Beta] ❌ Gemini API failed or quota exhausted. Refusing mock approval — "
            "a human reviewer must review this PR.",
            file=sys.stderr
        )
        sys.exit(1)
    
    response = response.strip()
    print(f"[Beta] Gemini: {response[:100]}...")

    if response.upper().startswith("APPROVED"):
        summary = response.partition("\n")[2].strip() or "Code meets all standards."
        gh.post_comment(pr_number, APPROVAL_COMMENT.format(summary=summary))
        gh.remove_label(pr_number, "needs-review")
        gh.ensure_label("approved", "0e8a16")
        gh.add_labels(pr_number, ["approved"])

        merged = gh.merge_pr(pr_number)
        if not merged:
            gh.append_log("Beta", f"PR #{pr_number}", "Approval posted but merge failed", "Merge Failed", "")
            print("[Beta] ⚠️  Approval posted but merge failed (branch protection?).")
            return

        queue["merge_count"] = queue.get("merge_count", 0) + 1
        in_prog = queue.get("in_progress") or {}
        if in_prog.get("pr_number") == pr_number:
            queue["in_progress"] = None
        gh.write_queue(queue)

        gh.append_log(
            "Beta", f"PR #{pr_number}",
            f"Approved and merged — merge_count={queue['merge_count']}",
            "Merged",
            brief[:100]
        )
        print(f"[Beta] ✅ PR #{pr_number} merged. merge_count={queue['merge_count']}")

        if queue["merge_count"] % 5 == 0:
            print("[Beta] Triggering governance cycle (Alpha).")
            gh.trigger_dispatch("governance-cycle")

    else:
        issues_md = "\n".join(
            line for line in response.splitlines()
            if line.strip().startswith(("-", "*"))
        ) or response
        gh.post_comment(pr_number, REJECTION_COMMENT.format(issues=issues_md))
        gh.ensure_label("changes-requested", "e11d48")
        gh.add_labels(pr_number, ["changes-requested"])
        gh.remove_label(pr_number, "needs-review")
        gh.append_log(
            "Beta", f"PR #{pr_number}",
            "Rejected — changes requested",
            "Changes Requested",
            issues_md[:200]
        )
        print(f"[Beta] ❌ PR #{pr_number} rejected.")


if __name__ == "__main__":
    main()
