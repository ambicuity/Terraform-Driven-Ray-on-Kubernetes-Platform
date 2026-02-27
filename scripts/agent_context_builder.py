#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
agent_context_builder.py — Reasoning Context Assembler for AI Agents.

Given a user query string (and optionally pre-computed query embedding),
assembles a structured ReasoningBundle containing:

  1. semantic_context     : Top-k semantically similar file/doc/issue/PR chunks
  2. structural_context   : Repo graph sub-graph for modules touched by top results
  3. historical_decisions : Relevant architectural decisions from decision_log.json
  4. recent_failures      : CI failure history for touched workflows
  5. performance_signals  : PERFORMANCE_CONSTRAINT decisions relevant to the query

Designed to be called by agents via CLI (subprocess) or imported directly.
Stdlib-only — safe for agent runtime use.

CLI Usage:
  python scripts/agent_context_builder.py \
    --query "how does the label swap race condition prevention work" \
    --memory-dir .memory \
    [--query-embedding-json '[0.01, -0.22, ...]'] \
    [--top-k 10] \
    [--output-format json]

Output: JSON to stdout (ReasoningBundle).

Note on query embedding: Agents that do not have sentence-transformers available
at runtime can pass --query-embedding-json as a pre-computed vector. When this
argument is omitted, the builder emits a zero-vector (keyword search only via
decision_log) with a warning. For full semantic retrieval, agents should compute
the query embedding in a CI step and cache it, or use the embedding endpoint.
"""

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from memory_retriever import MemoryRetriever, RetrievalResult
from memory_schemas import EMBEDDING_DIM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("agent_context_builder")


# ---------------------------------------------------------------------------
# ReasoningBundle dataclass
# ---------------------------------------------------------------------------

@dataclass
class ReasoningBundle:
    """
    Structured context bundle assembled for agent reasoning.
    All fields are JSON-serialisable.
    """
    query: str
    generated_at: str
    semantic_context: list[dict[str, Any]] = field(default_factory=list)
    structural_context: dict[str, Any] = field(default_factory=dict)
    historical_decisions: list[dict[str, Any]] = field(default_factory=list)
    recent_failures: list[dict[str, Any]] = field(default_factory=list)
    performance_signals: list[dict[str, Any]] = field(default_factory=list)
    # Metadata for traceability
    memory_dir: str = ""
    top_k_requested: int = 10
    query_embedding_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "generated_at": self.generated_at,
            "semantic_context": self.semantic_context,
            "structural_context": self.structural_context,
            "historical_decisions": self.historical_decisions,
            "recent_failures": self.recent_failures,
            "performance_signals": self.performance_signals,
            "_meta": {
                "memory_dir": self.memory_dir,
                "top_k_requested": self.top_k_requested,
                "query_embedding_available": self.query_embedding_available,
                "semantic_hits": len(self.semantic_context),
                "decision_hits": len(self.historical_decisions),
            },
        }


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

def _infer_touched_modules(results: list[RetrievalResult]) -> list[str]:
    """
    Infer the top-level module directories from semantic retrieval results.
    Used to scope structural and decision context retrieval.
    """
    modules: dict[str, int] = {}
    for r in results:
        top_dir = r.file_path.split("/")[0] if "/" in r.file_path else r.file_path
        modules[top_dir] = modules.get(top_dir, 0) + 1
    # Return modules sorted by hit count (most prominent first), cap at 5
    return [m for m, _ in sorted(modules.items(), key=lambda x: -x[1])][:5]


def _load_ci_failures(memory_dir: str, module_paths: list[str]) -> list[dict[str, Any]]:
    """Load CI failure history for workflows that reference touched modules."""
    ci_graph_path = os.path.join(memory_dir, "ci_graph.json")
    if not os.path.isfile(ci_graph_path):
        return []
    try:
        with open(ci_graph_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []

    failures = data.get("failure_history", [])
    if not failures:
        return []

    # Filter failures to workflows that depend on touched scripts
    touched_scripts = {f"scripts/{m}" if not m.startswith("scripts/") else m for m in module_paths}
    relevant_failures: list[dict[str, Any]] = []
    for wf in data.get("workflows", []):
        wf_scripts = set(wf.get("depends_on_scripts", []))
        if wf_scripts & touched_scripts:
            wf_name = wf["name"]
            relevant_failures.extend(
                [f for f in failures if f.get("workflow") == wf_name]
            )

    return sorted(relevant_failures, key=lambda f: f.get("timestamp", ""), reverse=True)[:5]


def build_context(
    query: str,
    query_embedding: list[float] | None,
    memory_dir: str,
    top_k: int = 10,
) -> ReasoningBundle:
    """
    Assemble a complete ReasoningBundle for a given query.

    Args:
        query: Natural language query string.
        query_embedding: Pre-computed 384-dim float vector, or None.
        memory_dir: Path to .memory/ directory.
        top_k: Number of semantic results to retrieve.

    Returns:
        ReasoningBundle ready for JSON serialisation.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    retriever = MemoryRetriever(memory_dir=memory_dir)

    bundle = ReasoningBundle(
        query=query,
        generated_at=now,
        memory_dir=memory_dir,
        top_k_requested=top_k,
        query_embedding_available=query_embedding is not None,
    )

    # --- 1. Semantic context ---
    if query_embedding and len(query_embedding) == EMBEDDING_DIM:
        results = retriever.top_k(query_embedding, k=top_k)
        bundle.semantic_context = [r.to_dict() for r in results]
        touched_modules = _infer_touched_modules(results)
    else:
        if query_embedding:
            logger.warning(
                "query_embedding has dimension %d; expected %d. Falling back to decision-only retrieval.",
                len(query_embedding), EMBEDDING_DIM,
            )
        else:
            logger.warning(
                "No query_embedding provided. Semantic retrieval disabled. "
                "Pass --query-embedding-json for full context."
            )
        results = []
        touched_modules = ["scripts", "terraform", "helm"]  # default to primary modules

    # --- 2. Structural context ---
    bundle.structural_context = retriever.load_structural_context(touched_modules)

    # --- 3. Historical decisions ---
    # Retrieve decisions touching the same modules, any type
    decisions = retriever.search_decisions(
        query_embedding=query_embedding or [],
        k=10,
        module=None,  # search across all modules
    )
    # Further filter to modules actually touched by semantic results
    if touched_modules and decisions:
        def _is_relevant(dec: dict) -> bool:
            related = dec.get("related_files", []) + [dec.get("source", "")]
            return any(
                any(rf.startswith(mod) for mod in touched_modules)
                for rf in related
            )
        relevant_decisions = [d for d in decisions if _is_relevant(d)]
        # If filtering removes everything, preserve all decisions
        bundle.historical_decisions = relevant_decisions if relevant_decisions else decisions
    else:
        bundle.historical_decisions = decisions

    # --- 4. Recent CI failures ---
    bundle.recent_failures = _load_ci_failures(memory_dir, touched_modules)

    # --- 5. Performance signals ---
    perf_signals = retriever.search_decisions(
        query_embedding=query_embedding or [],
        k=5,
        decision_type="PERFORMANCE_CONSTRAINT",
    )
    bundle.performance_signals = perf_signals

    return bundle


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble agent reasoning context from memory artifacts"
    )
    parser.add_argument("--query", required=True, help="Natural language query")
    parser.add_argument("--memory-dir", default=".memory", help="Path to .memory/ directory")
    parser.add_argument("--top-k", type=int, default=10, help="Number of semantic results")
    parser.add_argument(
        "--query-embedding-json",
        default=None,
        help="Pre-computed query embedding as JSON array string",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "pretty"],
        default="json",
        help="Output format: 'json' (compact) or 'pretty' (indented)",
    )
    args = parser.parse_args()

    # Parse query embedding
    query_embedding: list[float] | None = None
    if args.query_embedding_json:
        try:
            query_embedding = json.loads(args.query_embedding_json)
            if not isinstance(query_embedding, list):
                raise ValueError("Embedding must be a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Invalid --query-embedding-json: %s", exc)
            sys.exit(1)

    memory_dir = os.path.abspath(args.memory_dir)
    if not os.path.isdir(memory_dir):
        logger.warning("Memory directory not found: %s — results will be empty", memory_dir)

    bundle = build_context(
        query=args.query,
        query_embedding=query_embedding,
        memory_dir=memory_dir,
        top_k=args.top_k,
    )

    output = bundle.to_dict()
    if args.output_format == "pretty":
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
