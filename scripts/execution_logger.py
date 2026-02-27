#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
execution_logger.py — Agent Behavioral Memory Recorder.

Records structured execution outcomes for every agent run into
.memory/execution_log.json. This is the cognitive feedback loop:
agents learn from their own history, avoid repeating failures, and
detect recurring patterns.

Architecture:
  - Agents call log_execution() at the END of their run.
  - This module appends the record to execution_log.json via GitHub
    Contents API (same pattern as .ai_metadata/queue.json) so it
    works on ephemeral GitHub Actions runners.
  - CI embeds execution logs alongside code embeddings.
  - memory_retriever.py weights retrieval results by execution success rate.

Usage (agent integration):
  from execution_logger import log_execution, ExecutionRecord

  record = ExecutionRecord(
      agent="Delta",
      trigger_event="issue_labeled",
      trigger_source="issue/42",
      input_hash=sha256_of_issue_body,
      retrieved_context_ids=["file:scripts/gh_utils.py", "decision:ARCH-001"],
      decision_summary="Applied label-swap lock; generated fix for missing import guard",
      actions_taken=["label_swap", "pr_opened", "code_committed"],
      outcome="success",
      ci_status="green",
      duration_ms=elapsed_ms,
      confidence=0.88,
  )
  log_execution(record, repo_root=".")

Stdlib-only. Safe for agent runtime import.
"""

import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from memory_schemas import SCHEMA_VERSION, validate_execution_log, ValidationError

logger = logging.getLogger(__name__)

EXECUTION_LOG_PATH = os.path.join(".memory", "execution_log.json")
MAX_RUNS_IN_LOG = 1000  # Retain only the most recent N runs to limit file size

# Valid enum values — mirrors the schema so agents get early feedback on bad values
VALID_AGENTS = frozenset([
    "Alpha", "Beta", "Delta", "Gamma",
    "ai_issue_solver", "ai_test_engineer", "ai_duplicate_detector",
])
VALID_OUTCOMES = frozenset(["success", "failure", "partial", "skipped"])
VALID_ACTIONS = frozenset([
    "label_added", "label_removed", "label_swap",
    "comment_posted", "pr_opened", "pr_merged",
    "branch_created", "code_committed",
    "issue_closed", "issue_assigned",
    "duplicate_marked", "no_op",
])
VALID_CI_STATUSES = frozenset(["green", "red", "skipped", None])
VALID_EVENT_TYPES = frozenset([
    "issue_labeled", "pr_opened", "pr_merged", "schedule", "workflow_dispatch",
])


# ---------------------------------------------------------------------------
# ExecutionRecord dataclass
# ---------------------------------------------------------------------------

@dataclass
class ExecutionRecord:
    """
    Structured record of a single agent execution.

    All fields directly map to execution_log.schema.json.
    Agents construct this at the end of their run and call log_execution().
    """
    agent: str
    trigger_event: str  # VALID_EVENT_TYPES
    trigger_source: str  # e.g. "issue/42", "pr/7", "scheduled"
    input_hash: str  # sha256:... of primary input
    retrieved_context_ids: list[str]  # ["file:scripts/gh_utils.py", "decision:ARCH-001"]
    decision_summary: str
    actions_taken: list[str]  # ordered list from VALID_ACTIONS
    outcome: str  # VALID_OUTCOMES
    # Optional
    failure_reason: str = ""
    ci_status: str | None = None  # VALID_CI_STATUSES
    duration_ms: int = 0
    confidence: float = 0.0  # [0.0, 1.0]
    retry_count: int = 0
    context_retrieval_ms: int = 0

    def validate(self) -> None:
        """Fast pre-write validation. Raises ValueError on constraint violations."""
        if self.agent not in VALID_AGENTS:
            raise ValueError(f"Invalid agent '{self.agent}'. Must be one of {sorted(VALID_AGENTS)}")
        if self.trigger_event not in VALID_EVENT_TYPES:
            raise ValueError(f"Invalid trigger_event '{self.trigger_event}'")
        if self.outcome not in VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome '{self.outcome}'")
        for action in self.actions_taken:
            if action not in VALID_ACTIONS:
                raise ValueError(f"Invalid action '{action}'. Must be one of {sorted(VALID_ACTIONS)}")
        if self.ci_status not in VALID_CI_STATUSES:
            raise ValueError(f"Invalid ci_status '{self.ci_status}'")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if not self.input_hash.startswith("sha256:"):
            raise ValueError(f"input_hash must be prefixed 'sha256:', got '{self.input_hash[:20]}'")
        if len(self.decision_summary) > 500:
            raise ValueError(
                f"decision_summary exceeds 500 chars ({len(self.decision_summary)}). Truncate it."
            )
        if self.outcome == "failure" and not self.failure_reason:
            logger.warning(
                "outcome='failure' without failure_reason — consider adding context for future agents"
            )

    def to_json_record(self, run_id: str, timestamp: str) -> dict[str, Any]:
        """Serialize to the dict format expected by execution_log.json."""
        rec: dict[str, Any] = {
            "run_id": run_id,
            "agent": self.agent,
            "trigger": {
                "event_type": self.trigger_event,
                "source_ref": self.trigger_source,
            },
            "input_hash": self.input_hash,
            "retrieved_context_ids": self.retrieved_context_ids[:50],  # cap per schema
            "decision_summary": self.decision_summary[:500],
            "actions_taken": self.actions_taken,
            "outcome": self.outcome,
            "ci_status": self.ci_status,
            "duration_ms": self.duration_ms,
            "confidence": round(self.confidence, 4),
            "retry_count": self.retry_count,
            "context_retrieval_ms": self.context_retrieval_ms,
            "timestamp": timestamp,
        }
        # Only include failure_reason when relevant (keeps records clean)
        if self.failure_reason:
            rec["failure_reason"] = self.failure_reason[:300]
        return rec


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_input_hash(content: str) -> str:
    """
    Produce a deterministic SHA-256 hash of agent input content.
    Agents should hash the full issue/PR body + labels string.

    Example:
      input_hash = make_input_hash(f"{issue_title}\n{issue_body}\n{labels}")
    """
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def make_run_id(agent: str) -> tuple[str, str]:
    """
    Generate a deterministic run_id and timestamp for this execution.

    Returns:
      (run_id, timestamp_iso)  — both are strings.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id = f"{agent.lower()}-{ts}"
    return run_id, ts


def log_execution(
    record: ExecutionRecord,
    repo_root: str = ".",
    log_path: str | None = None,
) -> bool:
    """
    Append an execution record to execution_log.json.

    Handles:
      - Schema validation before write
      - Atomic append (load → prepend → truncate → write)
      - Max run cap (keeps last MAX_RUNS_IN_LOG records)

    Note on GitHub Actions runners: runners are ephemeral so execution_log.json
    must be committed via gh_utils.commit_file() after this call.

    Args:
        record: ExecutionRecord to persist.
        repo_root: Repository root (for resolving log_path).
        log_path: Override default path. Defaults to .memory/execution_log.json.

    Returns:
        True if written successfully, False on error.
    """
    try:
        record.validate()
    except ValueError as exc:
        logger.error("ExecutionRecord validation failed: %s", exc)
        return False

    run_id, timestamp = make_run_id(record.agent)
    json_record = record.to_json_record(run_id, timestamp)

    effective_path = log_path or os.path.join(repo_root, EXECUTION_LOG_PATH)

    # Load existing log
    existing_runs = _load_existing_runs(effective_path)

    # Prepend new record (most recent first)
    updated_runs = [json_record] + existing_runs

    # Enforce max cap
    if len(updated_runs) > MAX_RUNS_IN_LOG:
        logger.info(
            "Truncating execution log from %d to %d entries",
            len(updated_runs), MAX_RUNS_IN_LOG,
        )
        updated_runs = updated_runs[:MAX_RUNS_IN_LOG]

    log_envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "runs": updated_runs,
    }

    # Schema validation before write
    try:
        validate_execution_log(log_envelope)
    except ValidationError as exc:
        logger.error("execution_log validation failed before write: %s", exc)
        return False

    os.makedirs(os.path.dirname(effective_path), exist_ok=True)
    try:
        with open(effective_path, "w", encoding="utf-8") as fh:
            json.dump(log_envelope, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError as exc:
        logger.error("Failed to write execution_log.json: %s", exc)
        return False

    logger.info(
        "Execution logged: run_id=%s agent=%s outcome=%s confidence=%.2f",
        run_id, record.agent, record.outcome, record.confidence,
    )
    return True


def load_execution_history(
    repo_root: str = ".",
    agent: str | None = None,
    outcome: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Load recent execution history for retrieval weighting.

    Args:
        repo_root: Repository root.
        agent: Optional filter by agent name.
        outcome: Optional filter by outcome ("success", "failure", etc.).
        limit: Max records to return.

    Returns:
        List of run records, most recent first.
    """
    log_path = os.path.join(repo_root, EXECUTION_LOG_PATH)
    runs = _load_existing_runs(log_path)

    if agent:
        runs = [r for r in runs if r.get("agent") == agent]
    if outcome:
        runs = [r for r in runs if r.get("outcome") == outcome]

    return runs[:limit]


def compute_execution_success_weight(
    file_path: str,
    execution_history: list[dict[str, Any]],
) -> float:
    """
    Compute an execution success weight for a given file path.

    How it works:
      - Find all runs where this file appeared in retrieved_context_ids.
      - Weight = (successful runs) / (total runs that used this context).
      - Returns 0.5 if no history (neutral — neither boost nor penalty).
      - Returns higher for files that historically led to successful outcomes.

    This is the execution_success_weight component in the retrieval scoring:
      score = 0.6 * semantic + 0.2 * recency + 0.1 * execution_success + 0.1 * arch_relevance

    Args:
        file_path: Relative file path (e.g. "scripts/gh_utils.py").
        execution_history: List of run records from load_execution_history().

    Returns:
        Float in [0.0, 1.0]. 0.5 = no history.
    """
    context_key = f"file:{file_path}"
    relevant_runs = [
        r for r in execution_history
        if context_key in r.get("retrieved_context_ids", [])
    ]

    if not relevant_runs:
        return 0.5  # neutral prior

    successful = sum(1 for r in relevant_runs if r.get("outcome") == "success")
    return successful / len(relevant_runs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_existing_runs(log_path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(log_path):
        return []
    try:
        with open(log_path, encoding="utf-8") as fh:
            data = json.load(fh)
        runs = data.get("runs", [])
        if not isinstance(runs, list):
            return []
        return runs
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot load execution_log.json: %s — starting fresh", exc)
        return []
