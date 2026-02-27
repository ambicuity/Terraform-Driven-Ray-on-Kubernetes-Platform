#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
decision_extractor.py — Architectural Decision Memory Extractor.

Scans the entire repository for tagged architectural annotations and extracts
structured decision records into .memory/decision_log.json.

Recognised tags (in source comments or markdown):
  ARCH_DECISION:         Architectural design decisions
  SECURITY_BOUNDARY:     Trust boundary and permission decisions
  PERFORMANCE_CONSTRAINT: Performance requirement constraints

Also extracts:
  - ADR files (any markdown file whose name matches adr-*.md or ADR*.md)
  - PR body structured decisions (via pr_decisions passed as JSON arg)

Security: strips tokens, API keys, and long base64-like strings from
extracted content before writing to decision_log.json.

Usage:
  python scripts/decision_extractor.py \
    [--repo-root REPO_ROOT] \
    [--output-dir OUTPUT_DIR] \
    [--pr-number INT] \
    [--pr-body TEXT]

All stdlib. No third-party deps.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from memory_schemas import SCHEMA_VERSION, validate_decision_log, ValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("decision_extractor")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Source file extensions to scan for inline decision tags
SCAN_EXTENSIONS = frozenset([".py", ".tf", ".rego", ".yml", ".yaml", ".sh", ".hcl"])
# Markdown files: scan for ADRs and inline tags in docs/
DOC_EXTENSIONS = frozenset([".md"])
# All extensions to scan
ALL_SCAN_EXTENSIONS = SCAN_EXTENSIONS | DOC_EXTENSIONS

EXCLUDED_DIRS = frozenset([
    ".git", ".venv", ".venv-ray-test", "__pycache__", ".pytest_cache",
    ".terraform", "node_modules", ".memory",
])

# Tag patterns — capture tag type and the rest of the line as context
# Works in both # comment lines and <!-- markdown comments -->
_TAG_PATTERN = re.compile(
    r"(?:#|<!--|//)\s*(ARCH_DECISION|SECURITY_BOUNDARY|PERFORMANCE_CONSTRAINT)\s*:\s*(.+?)(?:-->)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Markdown heading-level ADR detection
_ADR_HEADING = re.compile(r"^#{1,3}\s+ADR[- _]?\d+", re.MULTILINE)
# Secret/token scrubbing: redact anything that looks like a 32+ char alphanumeric/base64 string
_SECRET_RE = re.compile(r"[A-Za-z0-9+/=]{32,}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decision_id(tag_type: str, source: str, index: int) -> str:
    """Generate a deterministic decision ID from tag type, source, and position."""
    raw = f"{tag_type}:{source}:{index}"
    short = hashlib.sha256(raw.encode()).hexdigest()[:8].upper()
    prefix = {"ARCH_DECISION": "ARCH", "SECURITY_BOUNDARY": "SEC", "PERFORMANCE_CONSTRAINT": "PERF",
               "PR_DECISION": "PR", "ADR": "ADR"}.get(tag_type, "DEC")
    return f"{prefix}-{short}"


def _scrub_secrets(text: str) -> str:
    """Redact any token-like strings from text before persisting to memory."""
    return _SECRET_RE.sub("[REDACTED]", text)


def extract_inline_tags(path: str, rel_path: str, repo_root: str) -> list[dict[str, Any]]:
    """
    Scan a file for ARCH_DECISION / SECURITY_BOUNDARY / PERFORMANCE_CONSTRAINT tags.
    Returns a list of decision dicts (without decision_id — assigned by caller).
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        logger.debug("Cannot read %s: %s", path, exc)
        return []

    decisions: list[dict[str, Any]] = []
    for match in _TAG_PATTERN.finditer(content):
        tag_type = match.group(1).upper()
        context_text = _scrub_secrets(match.group(2).strip())

        # Find approximate line number
        line_no = content[: match.start()].count("\n") + 1
        source = f"{rel_path}:{line_no}"

        decisions.append({
            "type": tag_type,
            "context": context_text,
            "rationale": "",
            "tradeoffs": "",
            "source": source,
            "related_files": [rel_path],
        })

    return decisions


def extract_adr_files(repo_root: str) -> list[dict[str, Any]]:
    """
    Find markdown ADR files (adr-*.md, ADR*.md) in docs/ or root, and extract
    their first paragraph as the decision context.
    """
    decisions: list[dict[str, Any]] = []
    docs_dir = os.path.join(repo_root, "docs")
    search_dirs = [repo_root, docs_dir] if os.path.isdir(docs_dir) else [repo_root]

    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for fname in os.listdir(search_dir):
            if not fname.lower().endswith(".md"):
                continue
            if not (re.match(r"^adr[-_ ]?\d+", fname, re.IGNORECASE) or
                    re.match(r"^ADR", fname)):
                continue
            abs_path = os.path.join(search_dir, fname)
            rel_path = os.path.relpath(abs_path, repo_root)
            try:
                with open(abs_path, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except OSError:
                continue

            # Extract title from first H1 heading
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else fname

            # Extract first non-empty paragraph after the heading
            paragraphs = [p.strip() for p in re.split(r"\n\n+", content) if p.strip()]
            context_text = paragraphs[1] if len(paragraphs) > 1 else paragraphs[0] if paragraphs else title
            context_text = _scrub_secrets(context_text[:500])

            decisions.append({
                "type": "ADR",
                "context": context_text,
                "rationale": "",
                "tradeoffs": "",
                "source": rel_path,
                "related_files": [rel_path],
            })

    return decisions


def extract_pr_decisions(pr_number: int, pr_body: str) -> list[dict[str, Any]]:
    """
    Extract ARCH_DECISION tags embedded in a pull request description.
    PR authors can document decisions directly in the PR body using the same
    tag syntax as inline code comments.
    """
    decisions: list[dict[str, Any]] = []
    for match in _TAG_PATTERN.finditer(pr_body):
        tag_type = match.group(1).upper()
        context_text = _scrub_secrets(match.group(2).strip())
        decisions.append({
            "type": "PR_DECISION" if tag_type not in ("ARCH_DECISION", "SECURITY_BOUNDARY", "PERFORMANCE_CONSTRAINT") else tag_type,
            "context": context_text,
            "rationale": "",
            "tradeoffs": "",
            "source": f"pr/{pr_number}",
            "related_files": [],
            "pr_number": pr_number,
        })
    return decisions


def load_existing_decisions(output_path: str) -> list[dict[str, Any]]:
    """Load existing decision_log.json. Returns existing decisions list."""
    if not os.path.isfile(output_path):
        return []
    try:
        with open(output_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data.get("decisions"), list):
            return []
        return data["decisions"]
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot load existing decision log: %s — starting fresh", exc)
        return []


def deduplicate_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove duplicate decisions based on decision_id.
    Preserves the most recent record when duplicates exist.
    """
    seen: dict[str, dict[str, Any]] = {}
    for dec in decisions:
        did = dec.get("decision_id", "")
        if did:
            seen[did] = dec  # last one wins (newest)
    return list(seen.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Architectural decision memory extractor")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--output-dir", default=".memory", help="Output directory")
    parser.add_argument("--pr-number", type=int, default=0, help="PR number for PR decision extraction")
    parser.add_argument("--pr-body", default="", help="PR body text for decision extraction")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    output_path = os.path.join(os.path.abspath(args.output_dir), "decision_log.json")
    now = _now_iso()

    logger.info("Starting decision extraction: root=%s", repo_root)

    # Load existing decisions to enable incremental append
    existing_decisions = load_existing_decisions(output_path)
    logger.info("Loaded %d existing decisions", len(existing_decisions))

    # Build set of known sources to avoid re-processing unchanged files
    known_sources: set[str] = {d.get("source", "").split(":")[0] for d in existing_decisions}

    new_decisions: list[dict[str, Any]] = []
    decision_index = 0

    # --- Scan source files for inline tags ---
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALL_SCAN_EXTENSIONS:
                continue
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, repo_root)
            tags = extract_inline_tags(abs_path, rel_path, repo_root)
            for tag in tags:
                tag["decision_id"] = _decision_id(tag["type"], rel_path, decision_index)
                tag["timestamp"] = now
                new_decisions.append(tag)
                decision_index += 1

    # --- Extract ADR files ---
    adr_decisions = extract_adr_files(repo_root)
    for adr in adr_decisions:
        adr["decision_id"] = _decision_id("ADR", adr["source"], decision_index)
        adr["timestamp"] = now
        new_decisions.append(adr)
        decision_index += 1

    # --- Extract PR body decisions ---
    if args.pr_number and args.pr_body:
        pr_decisions = extract_pr_decisions(args.pr_number, args.pr_body)
        for pr_dec in pr_decisions:
            pr_dec["decision_id"] = _decision_id(
                pr_dec["type"], pr_dec["source"], decision_index
            )
            pr_dec["timestamp"] = now
            new_decisions.append(pr_dec)
            decision_index += 1
        logger.info("Extracted %d decisions from PR #%d body", len(pr_decisions), args.pr_number)

    # Merge: new_decisions fully replaces scanning results; existing PR-only decisions preserved
    # Strategy: keep existing PR_DECISION and ADR records from history, replace inline scan results
    historical_pr_decisions = [d for d in existing_decisions if d.get("type") in ("PR_DECISION",)
                                and d.get("source", "").startswith("pr/")]
    all_decisions = new_decisions + [
        d for d in historical_pr_decisions
        if not any(n["decision_id"] == d["decision_id"] for n in new_decisions)
    ]
    all_decisions = deduplicate_decisions(all_decisions)

    # Sort by timestamp descending for readability
    all_decisions.sort(key=lambda d: d.get("timestamp", ""), reverse=True)

    decision_log: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "decisions": all_decisions,
    }

    try:
        validate_decision_log(decision_log)
    except ValidationError as exc:
        logger.error("decision_log validation failed: %s", exc)
        sys.exit(1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(decision_log, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    logger.info(
        "Decision extraction complete. Total decisions: %d (new: %d).",
        len(all_decisions), len(new_decisions),
    )


if __name__ == "__main__":
    main()
