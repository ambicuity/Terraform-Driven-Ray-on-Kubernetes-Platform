#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Agent Alpha (Project Lead) — Phase 4 of the Autonomous AI Engineering Lifecycle.

Triggered every 5 successful merges via 'governance-cycle' repository_dispatch
event (fired by Beta), or manually via workflow_dispatch.

Steps:
  1. Guard: merge_count - last_governance_merge >= 5 (prevents spurious runs).
  2. Fetch last 5 merged PRs → synthesise CHANGELOG.md entry via Gemini.
  3. Read ROADMAP.md → ask Gemini which milestones are now complete → mark them.
  4. Determine SemVer bump (feat/enhancement PRs → MINOR, else PATCH).
  5. Write CHANGELOG.md + ROADMAP.md via GitHub Contents API (protected against
     writing to .github/workflows/ by gh_utils._guard_protected_path).
  6. Create SemVer git tag.
  7. Delete merged ai-fix/ branches.
  8. Update queue.json last_governance_merge pointer.
  9. Append to INTERNAL_LOG.md.

Environment variables required:
  GEMINI_API_KEY, GITHUB_TOKEN, GITHUB_REPOSITORY
"""

import json
import re
import sys
from datetime import datetime, timezone

from gh_utils import (
    GeminiClient,
    GithubClient,
    GEMINI_MODEL_FLASH,
    require_env,
)

CHANGELOG_PROMPT = """\
# Role
You are the release manager for a Terraform/EKS/Ray repository. Your job is to produce
a machine-readable, human-auditable CHANGELOG entry following Keep-a-Changelog 1.0.0 format.

# Categorisation Rules (apply in order — first match wins)
- Added    → PR title starts with feat: or adds new resource / module / endpoint
- Changed  → PR title starts with refactor:, perf:, or modifies existing behaviour
- Fixed    → PR title starts with fix: or resolves a bug/regression
- Security → PR title starts with sec: or body mentions CVE / IAM / KMS / egress policy
- Chores (ci:, chore:, docs:) → OMIT from the changelog entry entirely

# Output Format (STRICT — do not deviate)
Begin your response with this exact line:
## [{version}] — {date}

Then one or more of these subsections (omit empty ones):
### Added
- One-sentence description. (#PR_NUMBER)

### Changed
- One-sentence description. (#PR_NUMBER)

### Fixed
- One-sentence description. (#PR_NUMBER)

### Security
- One-sentence description. (#PR_NUMBER)

# Rules
- Terse, engineering grammar. Active voice. No marketing language.
- Reference every PR number provided. Do not invent PR numbers.
- Do NOT include a preamble, heading above the ## line, or trailing prose.

# Merged PRs
{pr_list}
"""

ROADMAP_PROMPT = """\
# Role
You are reviewing a ROADMAP.md to determine which milestones the merged PRs have completed.
The ROADMAP uses a Markdown table where in-progress items have the cell text “🔄 In Progress”
and done items have “✅ Done”.

# Task
For each row in the ROADMAP table that is currently marked “🔄 In Progress”, decide whether
the merged PRs collectively deliver that milestone.

A milestone is COMPLETE only if the PRs demonstrably implement the feature described
in the milestone row. Do not mark a milestone complete based on partial work.

# Output Contract (STRICT)
Respond with a single raw JSON object. No markdown. No prose outside the JSON.
{{
  "completed_items": ["exact text of the feature cell from the ROADMAP table row"],
  "notes": "one sentence summarising which PRs completed which milestones"
}}

If no milestones are complete:
{{"completed_items": [], "notes": "No milestones fully completed by the merged PRs."}}

# ROADMAP.md (first 3000 chars)
{roadmap}

# Merged PRs
{pr_list}
"""


def determine_bump(prs: list) -> str:
    for pr in prs:
        labels = [lb["name"] for lb in pr.get("labels", [])]
        if any("enhancement" in lbl or "feature" in lbl for lbl in labels):
            return "minor"
        if re.search(r"\b(feat|feature|add|new)\b", pr.get("title", "").lower()):
            return "minor"
    return "patch"


def bump_version(current: str, bump: str) -> str:
    prefix = "v" if current.startswith("v") else ""
    parts = current.lstrip("v").split(".")
    if len(parts) != 3:
        return f"{prefix}1.0.1"
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump == "minor":
        return f"{prefix}{major}.{minor + 1}.0"
    return f"{prefix}{major}.{minor}.{patch + 1}"


def extract_version(changelog: str) -> str:
    m = re.search(r"##\s+\[v?([\d]+\.[\d]+\.[\d]+)\]", changelog)
    return f"v{m.group(1)}" if m else "v1.0.0"


def main() -> None:
    env = require_env("GEMINI_API_KEY", "GITHUB_TOKEN", "GITHUB_REPOSITORY")
    gh = GithubClient(env["GITHUB_TOKEN"], env["GITHUB_REPOSITORY"])
    gemini = GeminiClient(env["GEMINI_API_KEY"], model=GEMINI_MODEL_FLASH)  # governance: text synthesis, Flash sufficient

    queue = gh.read_queue()
    merge_count = queue.get("merge_count", 0)
    last_gov = queue.get("last_governance_merge", 0)

    if merge_count - last_gov < 5:
        print(f"[Alpha] merge_count={merge_count}, last_gov={last_gov}. No cycle needed.")
        sys.exit(0)

    print(f"[Alpha] Governance cycle at merge_count={merge_count}...")

    prs = gh.list_merged_prs(5)
    if not prs:
        print("[Alpha] No merged PRs found.", file=sys.stderr)
        sys.exit(1)

    pr_list_text = "\n\n".join(
        f"PR #{pr['number']}: {pr['title']}\n{(pr.get('body', '') or '')[:400]}"
        for pr in prs
    )

    # --- Version ---
    changelog, changelog_sha = gh.read_file("CHANGELOG.md")
    current_version = extract_version(changelog)
    bump = determine_bump(prs)
    new_version = bump_version(current_version, bump)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[Alpha] {current_version} → {new_version} ({bump})")

    # --- Synthesise CHANGELOG entry ---
    new_entry = gemini.generate(
        CHANGELOG_PROMPT.format(pr_list=pr_list_text, version=new_version, date=today),
        max_tokens=2048
    ).strip()
    if not new_entry:
        new_entry = (
            f"## [{new_version}] — {today}\n\n### Fixed\n"
            + "\n".join(f"- {pr['title']} (#{pr['number']})" for pr in prs)
        )

    header_end = changelog.find("\n## ")
    updated_changelog = (
        changelog[:header_end] + f"\n\n{new_entry}\n" + changelog[header_end:]
        if header_end != -1 else changelog + f"\n{new_entry}\n"
    )
    gh.write_file(
        "CHANGELOG.md", updated_changelog, changelog_sha,
        f"chore(release): update CHANGELOG for {new_version} [skip ci]"
    )
    print("[Alpha] CHANGELOG.md updated.")

    # --- Update ROADMAP ---
    roadmap, roadmap_sha = gh.read_file("ROADMAP.md")
    roadmap_json: dict = {}
    raw = gemini.generate(
        ROADMAP_PROMPT.format(roadmap=roadmap[:3000], pr_list=pr_list_text[:2000]),
        max_tokens=1024
    ).strip()
    try:
        roadmap_json = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass  # Fail safe; roadmap update is non-critical

    updated_roadmap = roadmap
    for item in roadmap_json.get("completed_items", []):
        updated_roadmap = updated_roadmap.replace(
            f"| {item} | 🔄 In Progress |",
            f"| {item} | ✅ Done |",
        )
    updated_roadmap = re.sub(
        r"## Current Version: v[\d.]+",
        f"## Current Version: {new_version}",
        updated_roadmap,
    )
    if updated_roadmap != roadmap:
        gh.write_file(
            "ROADMAP.md", updated_roadmap, roadmap_sha,
            f"chore(release): update ROADMAP for {new_version} [skip ci]"
        )
        print("[Alpha] ROADMAP.md updated.")

    # --- Tag ---
    main_sha = gh.get_main_sha()
    if main_sha:
        if gh.create_tag(new_version, main_sha):
            print(f"[Alpha] Tag {new_version} created.")
        else:
            print(f"[Alpha] Tag {new_version} may already exist.", file=sys.stderr)

    # --- Clean up merged ai-fix/ branches ---
    ai_branches = gh.list_branches(prefix="ai-fix/")
    for branch in ai_branches:
        gh.delete_branch(branch)
        print(f"[Alpha] Deleted branch: {branch}")

    # --- Update queue ---
    queue["last_governance_merge"] = merge_count
    gh.write_queue(queue)

    notes = roadmap_json.get("notes", "Governance cycle complete.")
    gh.append_log(
        "Alpha", "N/A",
        f"Governance: {current_version} → {new_version} ({bump} bump)",
        f"Released {new_version}",
        f"{notes} | Branches deleted: {ai_branches}"
    )
    print(f"[Alpha] ✅ Governance complete. Released {new_version}.")


if __name__ == "__main__":
    main()
