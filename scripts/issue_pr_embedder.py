#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
issue_pr_embedder.py — GitHub Issue and PR semantic embedding pipeline.

Fetches issue and PR metadata from GitHub REST API (via GithubClient),
embeds title + body text, and writes:
  - .memory/embeddings/issue_embeddings.json
  - .memory/embeddings/pr_embeddings.json

Incremental: compares title_hash to skip items whose content is unchanged.

IMPORTANT: Requires sentence_transformers — run only in CI, not at agent runtime.

Usage:
  python scripts/issue_pr_embedder.py \
    [--repo-root REPO_ROOT] \
    [--output-dir OUTPUT_DIR] \
    [--model-path MODEL_PATH] \
    [--max-issues N] [--max-prs N]

Environment variables:
  GITHUB_TOKEN        : Required for GitHub API access
  GITHUB_REPOSITORY   : owner/repo (e.g. ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform)
  MEMORY_MODEL_PATH   : Path to the cached sentence-transformers model directory
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from memory_schemas import (
    SCHEMA_VERSION,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    validate_embeddings,
    ValidationError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("issue_pr_embedder")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fetch_json(url: str, token: str) -> Any:
    """GET a GitHub API URL and return parsed JSON. Raises on error."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "memory-embedder",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("GitHub API %s → HTTP %s: %s", url, exc.code, body[:200])
        raise


def _load_existing(path: str) -> tuple[dict[str, str], list[dict]]:
    """Load existing embedding records. Returns (hash_lookup, records)."""
    if not os.path.isfile(path):
        return {}, []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}, []
    if data.get("model_name") != EMBEDDING_MODEL_NAME or data.get("model_version") != EMBEDDING_MODEL_VERSION:
        logger.warning("Model version mismatch in %s — discarding and regenerating", path)
        return {}, []
    records = data.get("embeddings", [])
    hash_lookup = {r["file_path"]: r.get("hash", "") for r in records}
    return hash_lookup, records


def _write_embedding_file(records: list[dict], output_path: str, label: str) -> None:
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model_name": EMBEDDING_MODEL_NAME,
        "model_version": EMBEDDING_MODEL_VERSION,
        "generated_at": _now_iso(),
        "embeddings": records,
    }
    try:
        validate_embeddings(envelope, os.path.basename(output_path))
    except ValidationError as exc:
        logger.error("%s validation failed: %s", label, exc)
        sys.exit(1)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    logger.info("Written: %s (%d records)", output_path, len(records))


def _load_model(model_path: str | None):
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("sentence-transformers not installed") from exc
    effective_path = model_path or os.environ.get("MEMORY_MODEL_PATH") or EMBEDDING_MODEL_NAME
    logger.info("Loading model: %s", effective_path)
    return SentenceTransformer(effective_path)


def embed_issues(
    token: str,
    repo: str,
    model: Any,
    output_dir: str,
    max_items: int,
) -> None:
    """Fetch issues, embed title+body, write issue_embeddings.json incrementally."""
    output_path = os.path.join(output_dir, "issue_embeddings.json")
    existing_hashes, existing_records = _load_existing(output_path)

    base_url = f"https://api.github.com/repos/{repo}"
    all_issues: list[dict] = []
    page = 1
    while len(all_issues) < max_items:
        url = f"{base_url}/issues?state=all&per_page=100&page={page}&sort=updated"
        try:
            batch = _fetch_json(url, token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch issues page %d: %s — stopping", page, exc)
            break
        if not isinstance(batch, list) or not batch:
            break
        # Filter out pull requests (GitHub API returns them as issues)
        all_issues.extend([i for i in batch if "pull_request" not in i])
        page += 1

    all_issues = all_issues[:max_items]
    logger.info("Fetched %d issues from GitHub", len(all_issues))

    existing_by_path = {r["file_path"]: r for r in existing_records}
    updated: list[dict] = []
    skipped = embedded = 0

    for issue in all_issues:
        number = issue.get("number", 0)
        file_path = f"issue/{number}"
        text = f"{issue.get('title', '')}\n\n{issue.get('body', '') or ''}"
        current_hash = _content_hash(text)

        if existing_hashes.get(file_path) == current_hash:
            updated.append(existing_by_path[file_path])
            skipped += 1
            continue

        vec = model.encode(text[:2048], normalize_embeddings=True)
        updated.append({
            "file_path": file_path,
            "hash": current_hash,
            "chunk_index": 0,
            "total_chunks": 1,
            "embedding": vec.tolist(),
        })
        embedded += 1

    logger.info("Issues: %d embedded, %d skipped (unchanged)", embedded, skipped)
    _write_embedding_file(updated, output_path, "issue_embeddings")


def embed_prs(
    token: str,
    repo: str,
    model: Any,
    output_dir: str,
    max_items: int,
) -> None:
    """Fetch PRs, embed title+body, write pr_embeddings.json incrementally."""
    output_path = os.path.join(output_dir, "pr_embeddings.json")
    existing_hashes, existing_records = _load_existing(output_path)

    base_url = f"https://api.github.com/repos/{repo}"
    all_prs: list[dict] = []
    page = 1
    while len(all_prs) < max_items:
        url = f"{base_url}/pulls?state=all&per_page=100&page={page}&sort=updated"
        try:
            batch = _fetch_json(url, token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch PRs page %d: %s — stopping", page, exc)
            break
        if not isinstance(batch, list) or not batch:
            break
        all_prs.extend(batch)
        page += 1

    all_prs = all_prs[:max_items]
    logger.info("Fetched %d PRs from GitHub", len(all_prs))

    existing_by_path = {r["file_path"]: r for r in existing_records}
    updated: list[dict] = []
    skipped = embedded = 0

    for pr in all_prs:
        number = pr.get("number", 0)
        file_path = f"pr/{number}"
        text = f"{pr.get('title', '')}\n\n{pr.get('body', '') or ''}"
        current_hash = _content_hash(text)

        if existing_hashes.get(file_path) == current_hash:
            updated.append(existing_by_path[file_path])
            skipped += 1
            continue

        vec = model.encode(text[:2048], normalize_embeddings=True)
        updated.append({
            "file_path": file_path,
            "hash": current_hash,
            "chunk_index": 0,
            "total_chunks": 1,
            "embedding": vec.tolist(),
        })
        embedded += 1

    logger.info("PRs: %d embedded, %d skipped (unchanged)", embedded, skipped)
    _write_embedding_file(updated, output_path, "pr_embeddings")


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue and PR semantic embedding pipeline")
    parser.add_argument("--output-dir", default=".memory/embeddings")
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--max-issues", type=int, default=500)
    parser.add_argument("--max-prs", type=int, default=500)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        logger.error("GITHUB_TOKEN and GITHUB_REPOSITORY environment variables are required")
        sys.exit(1)

    model = _load_model(args.model_path)

    embed_issues(token, repo, model, args.output_dir, args.max_issues)
    embed_prs(token, repo, model, args.output_dir, args.max_prs)
    logger.info("Issue and PR embedding complete.")


if __name__ == "__main__":
    main()
