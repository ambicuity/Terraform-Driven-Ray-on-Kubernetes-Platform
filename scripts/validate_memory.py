#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
validate_memory.py — CI Gate for Cognitive Memory Artifacts.

Enforces correctness guarantees on all .memory/ JSON artifacts before
they are committed to the repository. This script is the hard CI gate:
it exits with code 1 on any violation, preventing malformed or stale
memory from being merged into main.

Checks performed:
  1. Schema validation for all known memory files
  2. Total size budget (≤ 50 MB aggregate)
  3. Individual file size limits
  4. Embedding hash consistency: embedding records must reference files
     whose current on-disk hash matches the recorded hash
  5. Stale key detection: embedding records for files that no longer exist
  6. Model version tag consistency across all embedding files
  7. Decision log type validation
  8. JSON parseability (every file must be valid JSON)

Exit codes:
  0 — All checks passed
  1 — One or more checks failed

Usage:
  python scripts/validate_memory.py [--memory-dir .memory] [--repo-root .]
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from memory_schemas import (
    TOTAL_SIZE_LIMIT,
    SIZE_LIMITS,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    VALIDATORS,
    ValidationError,
    validate_file,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("validate_memory")

# Embedding files that have hash-linkage to repo files
_CODE_EMBEDDING_FILES = {"file_embeddings.json", "doc_embeddings.json"}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    except OSError:
        return "sha256:error"


def check_size_budgets(memory_dir: str) -> list[str]:
    """
    Check total aggregate size and individual file limits.
    Returns list of error messages (empty = pass).
    """
    errors: list[str] = []
    total_size = 0

    for root, dirs, files in os.walk(memory_dir):
        dirs[:] = [d for d in dirs if d != "schemas"]  # schemas are tiny, skip
        for fname in files:
            if not fname.endswith(".json"):
                continue
            abs_path = os.path.join(root, fname)
            try:
                size = os.path.getsize(abs_path)
            except OSError as exc:
                errors.append(f"Cannot stat {abs_path}: {exc}")
                continue

            total_size += size

            # Per-file limit check
            limit = SIZE_LIMITS.get(fname)
            if limit and size > limit:
                errors.append(
                    f"{fname}: size {size:,} bytes exceeds per-file limit "
                    f"{limit:,} bytes ({limit // (1024 * 1024)} MB)"
                )

    if total_size > TOTAL_SIZE_LIMIT:
        errors.append(
            f"Total memory size {total_size:,} bytes exceeds aggregate limit "
            f"{TOTAL_SIZE_LIMIT:,} bytes (50 MB). "
            "Shard embeddings by module or compress before committing."
        )

    logger.info("Total memory size: %s KB", total_size // 1024)
    return errors


def check_schema_validation(memory_dir: str) -> list[str]:
    """Validate schema of all known memory JSON files. Returns error list."""
    errors: list[str] = []
    for fname in VALIDATORS:
        # Determine path — embeddings are in a subdirectory
        if "embedding" in fname:
            abs_path = os.path.join(memory_dir, "embeddings", fname)
        else:
            abs_path = os.path.join(memory_dir, fname)

        if not os.path.isfile(abs_path):
            # Files requiring CI tools (sentence-transformers) or GitHub API are
            # optional at bootstrap. They are enforced once the CI memory build runs.
            optional_files = {
                "decision_log.json",
                "ci_graph.json",
                "file_embeddings.json",
                "doc_embeddings.json",
                "issue_embeddings.json",
                "pr_embeddings.json",
            }
            if fname in optional_files:
                logger.info("Optional file not yet generated: %s — skipping", fname)
                continue
            errors.append(f"Required memory file missing: {abs_path}")
            continue

        passed, msg = validate_file(abs_path)
        if not passed:
            errors.append(f"Schema validation failed for {fname}: {msg}")
        else:
            logger.info("✓ Schema valid: %s", fname)

    return errors


def check_embedding_hash_consistency(memory_dir: str, repo_root: str) -> list[str]:
    """
    Verify that embedding records whose file_path points to a repo file
    still have the same hash as the current on-disk file content.

    This catches the case where a file was modified but its embedding
    was not regenerated (would produce stale/misleading retrieval results).
    """
    errors: list[str] = []

    for embed_fname in _CODE_EMBEDDING_FILES:
        embed_path = os.path.join(memory_dir, "embeddings", embed_fname)
        if not os.path.isfile(embed_path):
            continue

        try:
            with open(embed_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{embed_fname}: cannot load for hash check — {exc}")
            continue

        # Group records by file_path to check once per file
        checked: set[str] = set()
        stale: list[str] = []
        missing: list[str] = []

        for rec in data.get("embeddings", []):
            rel_path = rec.get("file_path", "")
            if not rel_path or rel_path in checked:
                continue
            checked.add(rel_path)

            # Skip issue/ and pr/ virtual paths
            if rel_path.startswith(("issue/", "pr/")):
                continue

            abs_path = os.path.join(repo_root, rel_path)
            if not os.path.isfile(abs_path):
                missing.append(rel_path)
                continue

            current_hash = _sha256_file(abs_path)
            recorded_hash = rec.get("hash", "")
            if current_hash != recorded_hash:
                stale.append(rel_path)

        if stale:
            errors.append(
                f"{embed_fname}: {len(stale)} file(s) have stale embeddings "
                f"(content changed but not re-embedded). Run embedding_engine.py. "
                f"Example: {stale[0]}"
            )
        if missing:
            errors.append(
                f"{embed_fname}: {len(missing)} embedding record(s) reference files "
                f"that no longer exist in the repo (stale keys). "
                f"Run embedding_engine.py to prune. Example: {missing[0]}"
            )

    return errors


def check_model_version_consistency(memory_dir: str) -> list[str]:
    """
    Ensure all embedding files agree on model_name and model_version.
    Mixed versions corrupt retrieval quality by making embedding spaces incompatible.
    """
    errors: list[str] = []
    embed_dir = os.path.join(memory_dir, "embeddings")
    if not os.path.isdir(embed_dir):
        return errors

    for fname in os.listdir(embed_dir):
        if not fname.endswith(".json"):
            continue
        abs_path = os.path.join(embed_dir, fname)
        try:
            with open(abs_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        actual_model = data.get("model_name", "")
        actual_version = data.get("model_version", "")
        if actual_model and actual_model != EMBEDDING_MODEL_NAME:
            errors.append(
                f"{fname}: model_name is '{actual_model}', expected '{EMBEDDING_MODEL_NAME}'. "
                "All embedding files must use the same model. Regenerate embeddings."
            )
        if actual_version and actual_version != EMBEDDING_MODEL_VERSION:
            errors.append(
                f"{fname}: model_version is '{actual_version}', expected '{EMBEDDING_MODEL_VERSION}'. "
                "Run embedding_engine.py after upgrading the model."
            )

    return errors


def check_json_parseability(memory_dir: str) -> list[str]:
    """Verify all .json files in .memory/ are valid JSON (catches partial writes)."""
    errors: list[str] = []
    for root, dirs, files in os.walk(memory_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if not fname.endswith(".json"):
                continue
            abs_path = os.path.join(root, fname)
            try:
                with open(abs_path, encoding="utf-8") as fh:
                    json.load(fh)
            except json.JSONDecodeError as exc:
                errors.append(f"Invalid JSON in {abs_path}: {exc}")
            except OSError as exc:
                errors.append(f"Cannot read {abs_path}: {exc}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="CI validation gate for cognitive memory artifacts")
    parser.add_argument("--memory-dir", default=".memory", help="Path to .memory/ directory")
    parser.add_argument("--repo-root", default=".", help="Repository root (for hash linkage check)")
    args = parser.parse_args()

    memory_dir = os.path.abspath(args.memory_dir)
    repo_root = os.path.abspath(args.repo_root)

    if not os.path.isdir(memory_dir):
        logger.error("Memory directory not found: %s", memory_dir)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Cognitive Memory Validation — %s", memory_dir)
    logger.info("=" * 60)

    all_errors: list[str] = []

    # Check 1: JSON parseability (fast — catches partial writes early)
    logger.info("[1/5] Checking JSON parseability...")
    errs = check_json_parseability(memory_dir)
    all_errors.extend(errs)
    _log_check_result("JSON parseability", errs)

    # Check 2: Schema validation
    logger.info("[2/5] Checking schema validation...")
    errs = check_schema_validation(memory_dir)
    all_errors.extend(errs)
    _log_check_result("Schema validation", errs)

    # Check 3: Size budgets
    logger.info("[3/5] Checking size budgets...")
    errs = check_size_budgets(memory_dir)
    all_errors.extend(errs)
    _log_check_result("Size budgets", errs)

    # Check 4: Model version consistency
    logger.info("[4/5] Checking embedding model version consistency...")
    errs = check_model_version_consistency(memory_dir)
    all_errors.extend(errs)
    _log_check_result("Model version consistency", errs)

    # Check 5: Hash linkage (embedding hashes match current file content)
    logger.info("[5/5] Checking embedding hash consistency against repo files...")
    errs = check_embedding_hash_consistency(memory_dir, repo_root)
    all_errors.extend(errs)
    _log_check_result("Hash consistency", errs)

    logger.info("=" * 60)
    if all_errors:
        logger.error("VALIDATION FAILED — %d error(s):", len(all_errors))
        for i, err in enumerate(all_errors, 1):
            logger.error("  [%d] %s", i, err)
        sys.exit(1)
    else:
        logger.info("✅ VALIDATION PASSED — all memory artifacts are clean and consistent.")
        sys.exit(0)


def _log_check_result(name: str, errors: list[str]) -> None:
    if errors:
        for err in errors:
            logger.error("  ✗ %s: %s", name, err)
    else:
        logger.info("  ✓ %s: OK", name)


if __name__ == "__main__":
    main()
