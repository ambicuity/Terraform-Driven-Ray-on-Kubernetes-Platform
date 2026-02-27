#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
memory_retriever.py — Pure-Python cosine similarity retrieval engine.

Loads pre-computed embedding files from .memory/embeddings/ and performs
top-k retrieval using cosine similarity. No third-party libraries required —
uses only stdlib math module for vector operations.

This module is safe to import by agents at runtime.

API:
  retriever = MemoryRetriever(memory_dir=".memory")
  results = retriever.top_k(
      query_embedding=[...],   # pre-computed 384-dim float list
      k=10,
      file_type="python",      # optional filter
      module="scripts",        # optional filter (path prefix)
      after_date="2026-01-01", # optional ISO date filter
      tag=None,                # optional tag filter (for decisions)
  )

The query_embedding must be produced externally (e.g. by running:
  python -c "from sentence_transformers import SentenceTransformer; ..."
or by a lightweight local model). This module intentionally does NOT
import sentence_transformers to remain stdlib-only at agent runtime.
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_DIR_DEFAULT = ".memory"
EMBEDDING_FILES = {
    "file": "embeddings/file_embeddings.json",
    "doc": "embeddings/doc_embeddings.json",
    "issue": "embeddings/issue_embeddings.json",
    "pr": "embeddings/pr_embeddings.json",
}

# Recency decay: half-life of 30 days in seconds
_RECENCY_HALF_LIFE_SECONDS = 30 * 24 * 3600


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: str) -> float:
    """
    Parse an ISO 8601 timestamp string to POSIX seconds.
    Returns 0.0 on parse failure.
    """
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


def _recency_weight(record_timestamp_or_hash: str, now_ts: str) -> float:
    """
    Compute a recency weight for a record using exponential decay.

    Weight = exp(-λ × Δt) where λ = ln(2) / half_life.

    For embedding records, the timestamp is not stored directly — only the
    file hash. We therefore use 0.5 as the neutral prior at bootstrap.
    Once execution_log accumulates timestamps, this method can be upgraded
    to use per-run timestamps. Current implementation: neutral 0.5 unless
    the input looks like a valid ISO timestamp.

    Returns float in (0, 1].
    """
    # If the string looks like a timestamp, compute real decay
    if len(record_timestamp_or_hash) == 20 and "T" in record_timestamp_or_hash:
        record_ts = _parse_iso(record_timestamp_or_hash)
        now_posix = _parse_iso(now_ts)
        if record_ts > 0 and now_posix > 0:
            delta = max(0.0, now_posix - record_ts)
            lam = math.log(2) / _RECENCY_HALF_LIFE_SECONDS
            return math.exp(-lam * delta)
    # Neutral prior for records without timestamps
    return 0.5


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Pure-Python cosine similarity. No numpy required.

    Returns a float in [-1, 1]. Returns 0.0 for zero-magnitude vectors.
    Using iterative dot product and magnitude for memory efficiency.
    """
    if len(a) != len(b):
        return 0.0
    dot = 0.0
    mag_a = 0.0
    mag_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        mag_a += x * x
        mag_b += y * y
    denom = math.sqrt(mag_a) * math.sqrt(mag_b)
    if denom == 0.0:
        return 0.0
    return dot / denom


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """A single ranked retrieval result."""
    file_path: str
    score: float
    chunk_index: int
    total_chunks: int
    source_type: str  # "file", "doc", "issue", "pr"
    # Optional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "score": round(self.score, 6),
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "source_type": self.source_type,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class MemoryRetriever:
    """
    Cosine similarity retrieval over flat JSON embedding archives.

    Lazy-loads embedding files on first query to minimize memory usage
    in agents that may not need retrieval on every invocation.
    """

    def __init__(self, memory_dir: str = MEMORY_DIR_DEFAULT) -> None:
        self._memory_dir = os.path.abspath(memory_dir)
        self._corpora: dict[str, list[dict]] = {}  # source_type -> loaded records
        self._loaded: set[str] = set()

    def _load_corpus(self, source_type: str) -> list[dict]:
        """Lazy-load and cache a single embedding file."""
        if source_type in self._loaded:
            return self._corpora.get(source_type, [])

        rel_path = EMBEDDING_FILES.get(source_type)
        if not rel_path:
            logger.warning("Unknown source type: %s", source_type)
            self._loaded.add(source_type)
            return []

        abs_path = os.path.join(self._memory_dir, rel_path)
        if not os.path.isfile(abs_path):
            logger.info("Embedding file not found: %s — returning empty corpus", abs_path)
            self._loaded.add(source_type)
            return []

        try:
            with open(abs_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load %s: %s", abs_path, exc)
            self._loaded.add(source_type)
            return []

        records = data.get("embeddings", [])
        self._corpora[source_type] = records
        self._loaded.add(source_type)
        logger.debug("Loaded %d records from %s", len(records), abs_path)
        return records

    @staticmethod
    def _passes_filters(
        record: dict[str, Any],
        file_type: str | None,
        module: str | None,
        after_date: str | None,
    ) -> bool:
        """
        Apply optional pre-filters before computing cosine similarity.
        This avoids redundant dot-product operations on irrelevant records.
        """
        path = record.get("file_path", "")

        if file_type:
            ext_map = {
                "python": ".py",
                "terraform": ".tf",
                "rego": ".rego",
                "yaml": (".yml", ".yaml"),
                "markdown": ".md",
                "shell": ".sh",
            }
            expected_ext = ext_map.get(file_type)
            if expected_ext:
                if isinstance(expected_ext, tuple):
                    if not any(path.endswith(e) for e in expected_ext):
                        return False
                elif not path.endswith(expected_ext):
                    return False

        if module and not path.startswith(module):
            return False

        # Date filter not available from embedding record alone — skip for now
        # (decision_log has timestamps; embeddings only have hash)

        return True

    def top_k(
        self,
        query_embedding: list[float],
        k: int = 10,
        file_type: str | None = None,
        module: str | None = None,
        after_date: str | None = None,
        source_types: list[str] | None = None,
        use_weighted_scoring: bool = True,
    ) -> list[RetrievalResult]:
        """
        Retrieve the top-k most similar records with weighted composite scoring.

        Composite score formula (when use_weighted_scoring=True):
          score = 0.6 × semantic_similarity
                + 0.2 × recency_weight          (exponential decay, half-life 30 days)
                + 0.1 × execution_success_weight (from execution_log.json history)
                + 0.1 × architectural_relevance  (boosted if in decision_log sources)

        This transforms retrieval from pure cosine similarity into a
        weighted reasoning signal: recent, successful, architecturally-relevant
        context is preferred over semantically-similar-but-stale context.

        Args:
            query_embedding: Pre-computed query vector (must be 384-dim).
            k: Number of results to return.
            file_type: Optional filter: "python", "terraform", "rego", "yaml", "markdown".
            module: Optional path prefix filter (e.g. "scripts/", "terraform/").
            after_date: Optional ISO date string — hard filter on timestamp.
            source_types: Which corpora to include. Defaults to all four.
            use_weighted_scoring: If False, returns pure cosine similarity order.

        Returns:
            Sorted list of RetrievalResult, highest composite score first.
        """
        if not query_embedding:
            return []
        if source_types is None:
            source_types = list(EMBEDDING_FILES.keys())

        # Load scoring auxiliary data once (lazy)
        arch_relevant_paths = self._load_architecturally_relevant_paths()
        execution_weights = self._load_execution_success_weights()
        now_ts = _iso_now()

        all_results: list[RetrievalResult] = []

        for stype in source_types:
            records = self._load_corpus(stype)
            for rec in records:
                if not self._passes_filters(rec, file_type, module, after_date):
                    continue
                emb = rec.get("embedding")
                if not emb or not isinstance(emb, list):
                    continue

                file_path = rec.get("file_path", "")
                semantic = cosine_similarity(query_embedding, emb)

                if use_weighted_scoring:
                    recency = _recency_weight(rec.get("hash", ""), now_ts)
                    exec_success = execution_weights.get(file_path, 0.5)
                    arch_rel = 1.0 if file_path in arch_relevant_paths else 0.0
                    composite = (
                        0.6 * semantic
                        + 0.2 * recency
                        + 0.1 * exec_success
                        + 0.1 * arch_rel
                    )
                    score = composite
                    meta: dict[str, Any] = {
                        "semantic": round(semantic, 6),
                        "recency": round(recency, 4),
                        "exec_success": round(exec_success, 4),
                        "arch_relevance": arch_rel,
                    }
                else:
                    score = semantic
                    meta = {}

                all_results.append(RetrievalResult(
                    file_path=file_path,
                    score=score,
                    chunk_index=rec.get("chunk_index", 0),
                    total_chunks=rec.get("total_chunks", 1),
                    source_type=stype,
                    metadata=meta,
                ))

        # Sort by score descending, deduplicate by (file_path, chunk_index), take top-k
        all_results.sort(key=lambda r: r.score, reverse=True)
        seen: set[tuple[str, int]] = set()
        deduped: list[RetrievalResult] = []
        for r in all_results:
            key = (r.file_path, r.chunk_index)
            if key not in seen:
                seen.add(key)
                deduped.append(r)
            if len(deduped) >= k:
                break

        return deduped

    def _load_architecturally_relevant_paths(self) -> set[str]:
        """
        Load the set of file paths that appear in decision_log retrieved_context_ids.
        These receive the 0.1 architectural_relevance boost in weighted scoring.
        Cached after first call.
        """
        if hasattr(self, "_arch_paths"):
            return self._arch_paths  # type: ignore[return-value]

        paths: set[str] = set()
        # From decision_log.json related_files
        decision_log_path = os.path.join(self._memory_dir, "decision_log.json")
        if os.path.isfile(decision_log_path):
            try:
                with open(decision_log_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                for dec in data.get("decisions", []):
                    for rf in dec.get("related_files", []):
                        paths.add(rf)
            except (json.JSONDecodeError, OSError):
                pass

        # From execution_log.json retrieved_context_ids (file: prefix)
        exec_log_path = os.path.join(self._memory_dir, "execution_log.json")
        if os.path.isfile(exec_log_path):
            try:
                with open(exec_log_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                for run in data.get("runs", []):
                    for ctx_id in run.get("retrieved_context_ids", []):
                        if ctx_id.startswith("file:"):
                            paths.add(ctx_id[5:])
            except (json.JSONDecodeError, OSError):
                pass

        self._arch_paths = paths
        return paths

    def _load_execution_success_weights(self) -> dict[str, float]:
        """
        Load per-file execution success rates from execution_log.json.
        Returns {file_path: weight} where weight ∈ [0.0, 1.0].
        0.5 = no history (neutral prior).
        Cached after first call.
        """
        if hasattr(self, "_exec_weights"):
            return self._exec_weights  # type: ignore[return-value]

        weights: dict[str, float] = {}
        exec_log_path = os.path.join(self._memory_dir, "execution_log.json")
        if not os.path.isfile(exec_log_path):
            self._exec_weights = weights
            return weights

        try:
            with open(exec_log_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            self._exec_weights = weights
            return weights

        # Count successes and total uses per file context reference
        total_uses: dict[str, int] = {}
        success_uses: dict[str, int] = {}

        for run in data.get("runs", []):
            outcome = run.get("outcome", "")
            for ctx_id in run.get("retrieved_context_ids", []):
                if not ctx_id.startswith("file:"):
                    continue
                file_path = ctx_id[5:]
                total_uses[file_path] = total_uses.get(file_path, 0) + 1
                if outcome == "success":
                    success_uses[file_path] = success_uses.get(file_path, 0) + 1

        for file_path, total in total_uses.items():
            weights[file_path] = success_uses.get(file_path, 0) / total if total > 0 else 0.5

        self._exec_weights = weights
        return weights



    def search_decisions(
        self,
        query_embedding: list[float],
        k: int = 5,
        module: str | None = None,
        decision_type: str | None = None,
        after_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search decision_log.json for relevant architectural decisions.
        Uses cosine similarity if a decision has been embedded; otherwise
        falls back to keyword matching on context text.

        Note: decisions are not currently embedded separately — retrieval is
        keyword-based on context text. This avoids requiring embedding model
        at agent runtime while still providing high-signal context.
        """
        decision_log_path = os.path.join(self._memory_dir, "decision_log.json")
        if not os.path.isfile(decision_log_path):
            return []

        try:
            with open(decision_log_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cannot load decision_log: %s", exc)
            return []

        decisions = data.get("decisions", [])

        # Filter by type and module
        if decision_type:
            decisions = [d for d in decisions if d.get("type") == decision_type]
        if module:
            decisions = [
                d for d in decisions
                if any(f.startswith(module) for f in d.get("related_files", [d.get("source", "")]))
            ]
        if after_date:
            decisions = [d for d in decisions if d.get("timestamp", "") >= after_date]

        return decisions[:k]

    def load_structural_context(self, modules: list[str]) -> dict[str, Any]:
        """
        Load structural context (repo_graph + module_map) for the given module paths.
        Returns a filtered sub-graph relevant to the specified modules.
        """
        repo_graph_path = os.path.join(self._memory_dir, "repo_graph.json")
        module_map_path = os.path.join(self._memory_dir, "module_map.json")

        result: dict[str, Any] = {"nodes": [], "edges": [], "modules": []}

        # Load repo graph nodes and edges touching specified modules
        if os.path.isfile(repo_graph_path):
            try:
                with open(repo_graph_path, encoding="utf-8") as fh:
                    rg = json.load(fh)
                result["nodes"] = [
                    n for n in rg.get("nodes", [])
                    if any(n["path"].startswith(m.rstrip("/")) for m in modules)
                ]
                touched_paths = {n["path"] for n in result["nodes"]}
                result["edges"] = [
                    e for e in rg.get("edges", [])
                    if e.get("from") in touched_paths or e.get("to") in touched_paths
                ]
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Cannot load repo_graph: %s", exc)

        # Load module map entries for specified modules
        if os.path.isfile(module_map_path):
            try:
                with open(module_map_path, encoding="utf-8") as fh:
                    mm = json.load(fh)
                result["modules"] = [
                    mod for mod in mm.get("modules", [])
                    if any(mod["path"].startswith(m.rstrip("/")) for m in modules)
                ]
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Cannot load module_map: %s", exc)

        return result
