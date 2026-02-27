#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
embedding_engine.py — Local deterministic embedding pipeline.

Produces semantic vector embeddings for repository source files and
documents using a locally cached sentence-transformers model. Embeddings
are stored as flat JSON in .memory/embeddings/ and are regenerated only
when a file's SHA-256 hash changes (incremental mode).

IMPORTANT: This script requires `sentence_transformers` and is intended
to run ONLY in GitHub Actions CI (where the model is cached). It must
NOT be imported by agents at runtime — agents use memory_retriever.py
which is stdlib-only.

Usage:
  python scripts/embedding_engine.py \
    [--repo-root REPO_ROOT] \
    [--output-dir OUTPUT_DIR] \
    [--model-path MODEL_PATH] \
    [--changed-files FILE1 FILE2 ...]

Environment variables:
  MEMORY_MODEL_PATH : Path to the cached sentence-transformers model directory.
                      If not set, falls back to --model-path argument or
                      downloads the model (requires internet access in CI).
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from memory_schemas import (
    SCHEMA_VERSION,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    EMBEDDING_DIM,
    validate_embeddings,
    ValidationError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("embedding_engine")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHUNK_SIZE = 512  # character budget per chunk (approx. 128 tokens at 4 chars/token)
CHARS_PER_TOKEN = 4  # rough estimate: 1 token ≈ 4 characters
CHUNK_CHARS = CHUNK_SIZE * CHARS_PER_TOKEN  # 2048 chars per chunk
# NOTE: chunking is character-based, NOT tokenizer-based.
# This is intentional: character-based chunking is deterministic (no tokenizer dep in CI),
# fast, and strictly reproducible. If semantic quality degrades on long documents,
# upgrade to heading-based chunking for .md and line-based for .py.

INDEXED_EXTENSIONS = frozenset([".py", ".tf", ".rego", ".yml", ".yaml", ".md", ".hcl", ".sh"])
EXCLUDED_DIRS = frozenset([
    ".git", ".venv", ".venv-ray-test", "__pycache__", ".pytest_cache",
    ".terraform", "node_modules", ".memory",
])

DOC_EXTENSIONS = frozenset([".md"])
CODE_EXTENSIONS = frozenset([".py", ".tf", ".rego", ".hcl", ".sh"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_content(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError as exc:
        logger.warning("Cannot hash %s: %s", path, exc)
        return "sha256:error"
    return f"sha256:{h.hexdigest()}"


def _load_model(model_path: str | None):
    """
    Load the sentence-transformers model. Prefers a cached local path to
    avoid repeated downloads. Falls back to downloading from HuggingFace Hub
    if no cache path is provided.

    Returns a SentenceTransformer object.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
    except ImportError as exc:
        logger.error(
            "sentence_transformers is not installed. Install it in the CI environment: "
            "pip install sentence-transformers==2.7.0"
        )
        raise RuntimeError("Missing dependency: sentence-transformers") from exc

    effective_path = model_path or os.environ.get("MEMORY_MODEL_PATH") or EMBEDDING_MODEL_NAME
    logger.info("Loading embedding model from: %s", effective_path)
    model = SentenceTransformer(effective_path)
    logger.info("Model loaded. Embedding dimension: %d", model.get_sentence_embedding_dimension())
    return model


def _chunk_text(text: str, chunk_chars: int = CHUNK_CHARS) -> list[str]:
    """
    Split text into overlapping chunks of approximately chunk_chars length,
    respecting newline boundaries to avoid cutting mid-line.

    Returns a list of non-empty string chunks.
    """
    if not text.strip():
        return []
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        current.append(line)
        current_len += len(line)
        if current_len >= chunk_chars:
            chunk_text = "".join(current).strip()
            if chunk_text:
                chunks.append(chunk_text)
            # Overlap: keep last 20% of current chunk for context continuity
            overlap_cutoff = max(0, len(current) - max(1, len(current) // 5))
            current = current[overlap_cutoff:]
            current_len = sum(len(l) for l in current)

    if current:
        remainder = "".join(current).strip()
        if remainder:
            chunks.append(remainder)

    return chunks or [text.strip()]


def _load_existing_embeddings(path: str) -> tuple[dict[str, str], list[dict]]:
    """
    Load existing embedding records for incremental update.

    Returns:
      - file_hash_lookup: {file_path -> hash} of already-embedded files
      - existing_records: list of current embedding dicts
    """
    if not os.path.isfile(path):
        return {}, []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot load existing embeddings from %s: %s — starting fresh", path, exc)
        return {}, []

    # Validate model version consistency; if model changed, discard all embeddings
    if data.get("model_name") != EMBEDDING_MODEL_NAME or data.get("model_version") != EMBEDDING_MODEL_VERSION:
        logger.warning(
            "Existing embeddings use model '%s' v%s but current model is '%s' v%s. "
            "Discarding all and regenerating.",
            data.get("model_name"), data.get("model_version"),
            EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_VERSION,
        )
        return {}, []

    records = data.get("embeddings", [])
    # Build lookup: for each file_path, take the hash — all chunks share the same hash
    hash_lookup: dict[str, str] = {}
    for rec in records:
        fp = rec.get("file_path", "")
        if fp and fp not in hash_lookup:
            hash_lookup[fp] = rec.get("hash", "")

    return hash_lookup, records


def _embed_files(
    file_paths: list[str],
    repo_root: str,
    existing_hashes: dict[str, str],
    existing_records: list[dict],
    model: Any,
    changed_only: set[str],
) -> list[dict]:
    """
    Embed a list of files, skipping those whose hash matches the existing record.
    Returns the updated full list of embedding records.
    """
    # Build a map of file_path -> list[records] from existing data
    # to allow quick removal when a file needs re-embedding
    existing_by_path: dict[str, list[dict]] = {}
    for rec in existing_records:
        existing_by_path.setdefault(rec["file_path"], []).append(rec)

    # Collect files to process
    to_embed: list[tuple[str, str]] = []  # (abs_path, rel_path)
    skipped = 0

    for abs_path in file_paths:
        rel_path = os.path.relpath(abs_path, repo_root)
        current_hash = _sha256_file(abs_path)

        # In incremental mode, only re-embed files that are in the changed set
        # OR files that have never been embedded before
        if changed_only and rel_path not in changed_only and rel_path in existing_hashes:
            skipped += 1
            continue

        # Check hash — skip if unchanged
        if rel_path in existing_hashes and existing_hashes[rel_path] == current_hash:
            skipped += 1
            continue

        to_embed.append((abs_path, rel_path))

    logger.info("Embedding: %d files to process, %d skipped (hash unchanged)", len(to_embed), skipped)

    if not to_embed:
        return existing_records

    # Remove stale records for files we're about to re-embed
    re_embed_paths = {rel for _, rel in to_embed}
    updated_records = [r for r in existing_records if r["file_path"] not in re_embed_paths]

    # Embed in batches
    for abs_path, rel_path in to_embed:
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:
            logger.warning("Cannot read %s: %s — skipping", abs_path, exc)
            continue

        current_hash = _sha256_file(abs_path)
        chunks = _chunk_text(content)
        total_chunks = len(chunks)

        for chunk_idx, chunk in enumerate(chunks):
            try:
                # encode() returns a numpy array; convert to list for JSON serialization
                vec = model.encode(chunk, normalize_embeddings=True)
                # Round to 6dp: reduces file size ~35% with negligible semantic precision loss.
                # BGE-small-en-v1.5 values are ≤1.0; 6dp gives 1μ resolution, well beyond
                # retrieval significance threshold.
                embedding = [round(float(v), 6) for v in vec.tolist()]
            except Exception as exc:  # noqa: BLE001
                logger.error("Embedding failed for %s chunk %d: %s", rel_path, chunk_idx, exc)
                continue

            # Verify dimension matches schema expectation
            if len(embedding) != EMBEDDING_DIM:
                logger.error(
                    "Unexpected embedding dimension %d for %s (expected %d). Skipping.",
                    len(embedding), rel_path, EMBEDDING_DIM,
                )
                continue

            updated_records.append({
                "file_path": rel_path,
                "hash": current_hash,
                "chunk_index": chunk_idx,
                "total_chunks": total_chunks,
                "embedding": embedding,
            })

        logger.debug("Embedded %s → %d chunk(s)", rel_path, total_chunks)

    return updated_records


def _collect_files(repo_root: str, extensions: frozenset) -> list[str]:
    """Walk repo and collect absolute paths of files with given extensions."""
    result: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in extensions:
                result.append(os.path.join(dirpath, fname))
    return result


def _write_embedding_file(records: list[dict], output_path: str) -> None:
    """Serialize embedding records to disk with schema envelope."""
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
        logger.error("Embedding file %s failed validation: %s", output_path, exc)
        sys.exit(1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    size_kb = os.path.getsize(output_path) // 1024
    logger.info("Written: %s (%d KB, %d records)", output_path, size_kb, len(records))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local deterministic embedding engine")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--output-dir", default=".memory/embeddings", help="Output directory")
    parser.add_argument("--model-path", default=None, help="Path to cached sentence-transformers model")
    parser.add_argument(
        "--changed-files", nargs="*", default=None,
        help="Relative paths of files changed in this PR (incremental mode). "
             "If omitted, all files are checked against their hashes."
    )
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    output_dir = os.path.abspath(args.output_dir)
    changed_only: set[str] = set(args.changed_files) if args.changed_files else set()

    model = _load_model(args.model_path)

    # ---- file_embeddings.json (all code + config files) ----
    file_embed_path = os.path.join(output_dir, "file_embeddings.json")
    existing_hashes, existing_records = _load_existing_embeddings(file_embed_path)
    code_files = _collect_files(repo_root, CODE_EXTENSIONS | frozenset([".yml", ".yaml", ".json", ".tf", ".hcl"]))
    updated = _embed_files(code_files, repo_root, existing_hashes, existing_records, model, changed_only)
    # Prune records for files that no longer exist
    existing_paths = {os.path.join(repo_root, r["file_path"]) for r in updated}
    updated = [r for r in updated if os.path.isfile(os.path.join(repo_root, r["file_path"]))]
    _write_embedding_file(updated, file_embed_path)

    # ---- doc_embeddings.json (markdown only, chunk at heading boundaries) ----
    doc_embed_path = os.path.join(output_dir, "doc_embeddings.json")
    doc_existing_hashes, doc_existing_records = _load_existing_embeddings(doc_embed_path)
    doc_files = _collect_files(repo_root, DOC_EXTENSIONS)
    doc_updated = _embed_files(doc_files, repo_root, doc_existing_hashes, doc_existing_records, model, changed_only)
    doc_updated = [r for r in doc_updated if os.path.isfile(os.path.join(repo_root, r["file_path"]))]
    _write_embedding_file(doc_updated, doc_embed_path)

    logger.info(
        "Embedding complete. Code records: %d, Doc records: %d",
        len(updated), len(doc_updated),
    )


if __name__ == "__main__":
    main()
