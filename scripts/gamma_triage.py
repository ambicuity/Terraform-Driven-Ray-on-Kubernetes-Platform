#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Agent Gamma (Triager) — Phase 1 of the Autonomous AI Engineering Lifecycle.

Triggered when a new GitHub issue is opened. This agent:
  1. Checks for duplicate issues using a GEMINI SEMANTIC SIMILARITY call
     (replacing the brittle word-overlap heuristic).
  2. Validates three required technical markers in the issue body.
  3. If markers are missing  → posts "needs-info" comment + label → terminates.
  4. If semantically duplicate → posts notice + label → terminates.
  5. If valid               → assigns priority label + status:triaged, writes a Technical
                               Brief to .ai_metadata/queue.json, appends to INTERNAL_LOG.md.

Environment variables required:
  GEMINI_API_KEY, GITHUB_TOKEN, ISSUE_NUMBER, GITHUB_REPOSITORY
"""

import json
import os
import re
import sys

from gh_utils import (
    GeminiClient,
    GithubClient,
    GEMINI_MODEL_FLASH,
    require_env,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PRIORITY_HIGH = re.compile(
    r"\b(crash|data.?loss|security|outage|production|critical|regression|broken|oom|evict|flood)\b",
    re.IGNORECASE,
)
PRIORITY_LOW = re.compile(
    r"\b(typo|doc|documentation|readme|style|cosmetic|nit|minor|question|how.?to)\b",
    re.IGNORECASE,
)
MARKER_PATTERNS = {
    "environment": re.compile(
        r"\b(env|environment|os|version|platform|cluster|eks|k8s|kubernetes|terraform|python)\b",
        re.IGNORECASE,
    ),
    "steps_to_reproduce": re.compile(
        r"\b(reproduce|repro|step|run|command|exec|kubectl|terraform|tried|attempt)\b",
        re.IGNORECASE,
    ),
    "expected_vs_actual": re.compile(
        r"\b(expected|actual|should|but got|result|behaviour|behavior|output|error|fail|instead)\b",
        re.IGNORECASE,
    ),
}
BOT_HEADER = "<!-- gamma-triage-bot -->"

NEEDS_INFO_TEMPLATE = """\
{bot_header}
## 🔍 Agent Gamma — Needs More Information

Before this issue can be triaged, please provide the following:

{missing_sections}

### Required Format

```
### Environment Info
- OS / Platform:
- Terraform / EKS / Ray version:

### Steps to Reproduce
1. ...

### Expected vs Actual Output
- Expected: ...
- Actual: ...
```

---
*Automated triage by Agent Gamma · Powered by Gemini AI*
"""

DUPLICATE_TEMPLATE = """\
{bot_header}
## 🔁 Agent Gamma — Possible Duplicate Detected

This issue appears to describe the same problem as:

{matches}

If your issue is different, edit the description to clarify. The bot will re-evaluate.

---
*Automated semantic duplicate detection by Agent Gamma · Powered by Gemini AI*
"""

PRIORITY_COLORS = {
    "priority:high": "d73a4a",
    "priority:medium": "e4a900",
    "priority:low": "0075ca",
}


# ---------------------------------------------------------------------------
# Semantic duplicate detection via Gemini
# ---------------------------------------------------------------------------

def detect_duplicates_semantic(issue: dict, closed_issues: list, gemini: GeminiClient) -> list[dict]:
    """
    Use Gemini to perform semantic similarity on issue titles + bodies.
    This replaces word-overlap, which misses "App crashes on start" vs
    "Initialization fails with SIGSEGV" — two descriptions of the same bug.
    Returns a list of {number, title, url} for semantically similar closed issues.
    """
    if not closed_issues:
        return []

    # Exclude self from the comparison set
    candidates = [c for c in closed_issues if str(c.get("number")) != str(issue.get("number"))]
    if not candidates:
        return []

    candidates_summary = "\n".join(
        f"Issue #{c['number']}: {c.get('title', '')} — {(c.get('body') or '')[:200]}"
        for c in candidates[:10]
    )
    prompt = (
        "You are a senior engineer reviewing GitHub issues for a Terraform/EKS/Ray repository.\n"
        "Determine if the NEW ISSUE is semantically the same as any EXISTING ISSUE below.\n"
        "Two issues are duplicates if they describe the same underlying bug or request,\n"
        "even if worded completely differently.\n\n"
        f"NEW ISSUE:\nTitle: {issue.get('title', '')}\n"
        f"Body: {(issue.get('body') or '')[:500]}\n\n"
        f"EXISTING ISSUES:\n{candidates_summary}\n\n"
        "Respond ONLY with a JSON array of issue numbers that are semantic duplicates.\n"
        "Example: [12, 34] or [] if none.\n"
        "Do not include any other text."
    )
    raw = gemini.generate(prompt, temperature=0.1, max_tokens=128).strip()
    try:
        dup_numbers = set(json.loads(raw))
    except (json.JSONDecodeError, ValueError):
        return []  # Gemini returned unexpected format — fail safe (not fail loud)

    return [
        {"number": c["number"], "title": c.get("title", ""), "url": c.get("html_url", "")}
        for c in candidates
        if c.get("number") in dup_numbers
    ]


# ---------------------------------------------------------------------------
# Marker validation
# ---------------------------------------------------------------------------

def validate_markers(body: str) -> list[str]:
    return [name for name, pattern in MARKER_PATTERNS.items() if not pattern.search(body)]


# ---------------------------------------------------------------------------
# Priority assignment
# ---------------------------------------------------------------------------

def assign_priority(issue: dict) -> str:
    text = f"{issue.get('title', '')} {issue.get('body', '')}"
    if PRIORITY_HIGH.search(text):
        return "priority:high"
    if PRIORITY_LOW.search(text):
        return "priority:low"
    return "priority:medium"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    env = require_env("GEMINI_API_KEY", "GITHUB_TOKEN", "ISSUE_NUMBER", "GITHUB_REPOSITORY")
    gh = GithubClient(env["GITHUB_TOKEN"], env["GITHUB_REPOSITORY"])
    gemini = GeminiClient(env["GEMINI_API_KEY"], model=GEMINI_MODEL_FLASH)  # triage: speed > reasoning
    issue_number = int(env["ISSUE_NUMBER"])

    print(f"[Gamma] Triaging issue #{issue_number} in {env['GITHUB_REPOSITORY']}...")

    issue = gh.get_issue(issue_number)
    if not issue:
        print("[Gamma] Could not fetch issue. Aborting.", file=sys.stderr)
        sys.exit(1)

    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    print(f"[Gamma] Issue: {title}")

    # --- Semantic duplicate detection (Gemini, not word overlap) ---
    closed = gh.list_issues(state="closed", per_page=10)
    duplicates = detect_duplicates_semantic(issue, closed, gemini)
    if duplicates:
        matches_md = "\n".join(
            f"- [#{d['number']} — {d['title']}]({d['url']})" for d in duplicates
        )
        gh.post_comment(issue_number, DUPLICATE_TEMPLATE.format(
            bot_header=BOT_HEADER, matches=matches_md
        ))
        gh.ensure_label("duplicate", "cfd3d7")
        gh.add_labels(issue_number, ["duplicate"])
        gh.append_log(
            "Gamma", f"#{issue_number}",
            "Detected semantic duplicate",
            "Blocked — pending user clarification",
            f"Duplicates: {[d['number'] for d in duplicates]}"
        )
        print("[Gamma] Semantic duplicate detected. Terminating.")
        return

    # --- Marker validation ---
    missing_markers = validate_markers(body)
    if missing_markers:
        sections = "\n".join(
            f"- ❌ **{m.replace('_', ' ').title()}**" for m in missing_markers
        )
        gh.post_comment(issue_number, NEEDS_INFO_TEMPLATE.format(
            bot_header=BOT_HEADER, missing_sections=sections
        ))
        gh.ensure_label("needs-info", "e4e669")
        gh.add_labels(issue_number, ["needs-info"])
        gh.append_log(
            "Gamma", f"#{issue_number}",
            "Posted needs-info comment",
            "Blocked — awaiting user info",
            f"Missing: {missing_markers}"
        )
        print(f"[Gamma] Missing markers: {missing_markers}. Terminating.")
        return

    # --- Valid issue: triage ---
    priority = assign_priority(issue)
    print(f"[Gamma] Priority: {priority}")
    gh.ensure_label(priority, PRIORITY_COLORS[priority])
    gh.ensure_label("status:triaged", "bfd4f2")
    gh.add_labels(issue_number, [priority, "status:triaged"])

    # Generate Technical Brief
    brief_prompt = (
        "Write a 2-3 sentence Technical Brief for the following GitHub issue. "
        "Be concise and engineering-focused. No bullets.\n\n"
        f"Title: {title}\nBody:\n{body[:2000]}"
    )
    brief = gemini.generate(brief_prompt).strip() or title

    # Write to queue (via Contents API — persists across runner boundaries)
    queue = gh.read_queue()
    order = {"high": 0, "medium": 1, "low": 2}
    entry = {
        "issue_number": issue_number,
        "title": title,
        "priority": priority.split(":")[1],
        "brief": brief,
        "branch": f"ai-fix/{issue_number}",
        "url": issue.get("html_url", ""),
    }
    queue["queued"].append(entry)
    queue["queued"].sort(key=lambda e: order.get(e.get("priority", "low"), 2))
    gh.write_queue(queue)

    gh.append_log(
        "Gamma", f"#{issue_number}",
        f"Triaged — {priority}; added to queue",
        "Queued → awaiting Delta",
        f"Brief: {brief[:120]}"
    )
    print(f"[Gamma] ✅ Issue #{issue_number} triaged.")


if __name__ == "__main__":
    main()
