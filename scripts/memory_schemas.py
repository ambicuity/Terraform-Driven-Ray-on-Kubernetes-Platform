#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
memory_schemas.py — JSON schema constants and validation helpers for the
cognitive memory layer.

All schema validation uses stdlib `json` and `re` only. No third-party
jsonschema library is required — we implement a targeted structural
validator that validates required fields and types for each memory file.

This module is importable by both CI scripts (embedding_engine, validate_memory)
and agents at runtime without any additional dependencies.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema version — bump this when any schema field changes
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_MODEL_VERSION = "0.1.0"
EMBEDDING_DIM = 384

# ---------------------------------------------------------------------------
# Size limits (bytes)
# ---------------------------------------------------------------------------
SIZE_LIMITS: dict[str, int] = {
    "file_embeddings.json": 15 * 1024 * 1024,   # 15 MB
    "doc_embeddings.json": 5 * 1024 * 1024,     # 5 MB
    "issue_embeddings.json": 5 * 1024 * 1024,   # 5 MB
    "pr_embeddings.json": 5 * 1024 * 1024,      # 5 MB
    "repo_graph.json": 3 * 1024 * 1024,         # 3 MB
    "module_map.json": 1 * 1024 * 1024,         # 1 MB
    "dependency_graph.json": 1 * 1024 * 1024,   # 1 MB
    "infra_graph.json": 2 * 1024 * 1024,        # 2 MB
    "ci_graph.json": 1 * 1024 * 1024,           # 1 MB
    "decision_log.json": 2 * 1024 * 1024,       # 2 MB
    "execution_log.json": 5 * 1024 * 1024,      # 5 MB (1000 runs × ~5KB each)
}
TOTAL_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB

# ---------------------------------------------------------------------------
# Decision tag types recognised by decision_extractor.py
# ---------------------------------------------------------------------------
DECISION_TYPES = frozenset([
    "ARCH_DECISION",
    "SECURITY_BOUNDARY",
    "PERFORMANCE_CONSTRAINT",
    "PR_DECISION",
    "ADR",
])

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when a memory artifact fails schema validation."""


def _require_keys(obj: dict[str, Any], keys: list[str], context: str) -> None:
    """Assert that all required keys are present in the dict."""
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValidationError(f"{context}: missing required keys: {missing}")


def _require_type(value: Any, expected_type: type, field: str, context: str) -> None:
    """Assert that a value is the expected type."""
    if not isinstance(value, expected_type):
        raise ValidationError(
            f"{context}: field '{field}' must be {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )


def _require_schema_version(obj: dict[str, Any], context: str) -> None:
    """Validate schema_version field."""
    _require_keys(obj, ["schema_version"], context)
    if obj["schema_version"] != SCHEMA_VERSION:
        raise ValidationError(
            f"{context}: schema_version must be '{SCHEMA_VERSION}', "
            f"got '{obj['schema_version']}'"
        )


# ---------------------------------------------------------------------------
# Per-file validators
# ---------------------------------------------------------------------------

def validate_repo_graph(data: dict[str, Any]) -> None:
    """Validate repo_graph.json structure."""
    ctx = "repo_graph"
    _require_schema_version(data, ctx)
    _require_keys(data, ["generated_at", "nodes", "edges", "metrics"], ctx)
    _require_type(data["nodes"], list, "nodes", ctx)
    _require_type(data["edges"], list, "edges", ctx)
    _require_type(data["metrics"], dict, "metrics", ctx)

    valid_node_types = {"python", "terraform", "helm", "rego", "yaml", "markdown", "json", "shell", "other"}
    for i, node in enumerate(data["nodes"]):
        node_ctx = f"{ctx}.nodes[{i}]"
        _require_keys(node, ["path", "type", "size_bytes", "hash"], node_ctx)
        if node["type"] not in valid_node_types:
            raise ValidationError(f"{node_ctx}: invalid type '{node['type']}'")
        if not isinstance(node["size_bytes"], int) or node["size_bytes"] < 0:
            raise ValidationError(f"{node_ctx}: size_bytes must be non-negative integer")

    valid_edge_relations = {"imports", "calls", "references", "configures", "deploys", "tests", "documents"}
    for i, edge in enumerate(data["edges"]):
        edge_ctx = f"{ctx}.edges[{i}]"
        _require_keys(edge, ["from", "to", "relation"], edge_ctx)
        if edge["relation"] not in valid_edge_relations:
            raise ValidationError(f"{edge_ctx}: invalid relation '{edge['relation']}'")

    _require_keys(data["metrics"], ["total_files", "python_files", "terraform_files"], f"{ctx}.metrics")


def validate_module_map(data: dict[str, Any]) -> None:
    """Validate module_map.json structure."""
    ctx = "module_map"
    _require_schema_version(data, ctx)
    _require_keys(data, ["generated_at", "modules"], ctx)
    _require_type(data["modules"], list, "modules", ctx)

    valid_types = {"python_package", "terraform_module", "helm_chart", "rego_policy", "ci_workflow", "docs", "yaml", "other"}
    for i, mod in enumerate(data["modules"]):
        mod_ctx = f"{ctx}.modules[{i}]"
        _require_keys(mod, ["name", "path", "type", "files"], mod_ctx)
        if mod["type"] not in valid_types:
            raise ValidationError(f"{mod_ctx}: invalid type '{mod['type']}'")
        _require_type(mod["files"], list, "files", mod_ctx)


def validate_dependency_graph(data: dict[str, Any]) -> None:
    """Validate dependency_graph.json structure."""
    ctx = "dependency_graph"
    _require_schema_version(data, ctx)
    _require_keys(data, ["generated_at", "dependencies"], ctx)
    _require_type(data["dependencies"], list, "dependencies", ctx)

    valid_types = {
        "direct_import", "transitive_import",
        "terraform_module_ref", "helm_dependency", "ci_uses_script"
    }
    for i, dep in enumerate(data["dependencies"]):
        dep_ctx = f"{ctx}.dependencies[{i}]"
        _require_keys(dep, ["source", "target", "type", "depth"], dep_ctx)
        if dep["type"] not in valid_types:
            raise ValidationError(f"{dep_ctx}: invalid type '{dep['type']}'")
        if not isinstance(dep["depth"], int) or dep["depth"] < 1:
            raise ValidationError(f"{dep_ctx}: depth must be positive integer")


def validate_infra_graph(data: dict[str, Any]) -> None:
    """Validate infra_graph.json structure."""
    ctx = "infra_graph"
    _require_schema_version(data, ctx)
    _require_keys(data, ["generated_at", "terraform", "helm"], ctx)
    _require_type(data["terraform"], dict, "terraform", ctx)
    _require_type(data["helm"], dict, "helm", ctx)
    _require_keys(data["terraform"], ["resources", "modules", "providers"], f"{ctx}.terraform")
    _require_keys(data["helm"], ["charts"], f"{ctx}.helm")


def validate_ci_graph(data: dict[str, Any]) -> None:
    """Validate ci_graph.json structure."""
    ctx = "ci_graph"
    _require_schema_version(data, ctx)
    _require_keys(data, ["generated_at", "workflows", "failure_history"], ctx)
    _require_type(data["workflows"], list, "workflows", ctx)
    _require_type(data["failure_history"], list, "failure_history", ctx)

    for i, wf in enumerate(data["workflows"]):
        wf_ctx = f"{ctx}.workflows[{i}]"
        _require_keys(wf, ["name", "path", "triggers", "jobs"], wf_ctx)


def validate_decision_log(data: dict[str, Any]) -> None:
    """Validate decision_log.json structure."""
    ctx = "decision_log"
    _require_schema_version(data, ctx)
    _require_keys(data, ["decisions"], ctx)
    _require_type(data["decisions"], list, "decisions", ctx)

    valid_types = DECISION_TYPES
    for i, dec in enumerate(data["decisions"]):
        dec_ctx = f"{ctx}.decisions[{i}]"
        _require_keys(dec, ["decision_id", "type", "context", "source", "timestamp", "related_files"], dec_ctx)
        if dec["type"] not in valid_types:
            raise ValidationError(f"{dec_ctx}: invalid type '{dec['type']}'")
        _require_type(dec["related_files"], list, "related_files", dec_ctx)


def validate_execution_log(data: dict[str, Any]) -> None:
    """Validate execution_log.json structure."""
    ctx = "execution_log"
    _require_schema_version(data, ctx)
    _require_keys(data, ["runs"], ctx)
    _require_type(data["runs"], list, "runs", ctx)

    valid_agents = {
        "Alpha", "Beta", "Delta", "Gamma",
        "ai_issue_solver", "ai_test_engineer", "ai_duplicate_detector",
    }
    valid_outcomes = {"success", "failure", "partial", "skipped"}
    valid_ci_statuses = {"green", "red", "skipped"}
    valid_actions = {
        "label_added", "label_removed", "label_swap",
        "comment_posted", "pr_opened", "pr_merged",
        "branch_created", "code_committed",
        "issue_closed", "issue_assigned",
        "duplicate_marked", "no_op",
    }

    for i, run in enumerate(data["runs"]):
        run_ctx = f"{ctx}.runs[{i}]"
        _require_keys(
            run,
            ["run_id", "agent", "trigger", "input_hash",
             "retrieved_context_ids", "decision_summary",
             "actions_taken", "outcome", "timestamp"],
            run_ctx,
        )
        if run["agent"] not in valid_agents:
            raise ValidationError(f"{run_ctx}: invalid agent '{run['agent']}'")
        if run["outcome"] not in valid_outcomes:
            raise ValidationError(f"{run_ctx}: invalid outcome '{run['outcome']}'")
        for action in run.get("actions_taken", []):
            if action not in valid_actions:
                raise ValidationError(f"{run_ctx}: invalid action '{action}'")
        ci_status = run.get("ci_status")
        if ci_status is not None and ci_status not in valid_ci_statuses:
            raise ValidationError(f"{run_ctx}: invalid ci_status '{ci_status}'")
        confidence = run.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            raise ValidationError(f"{run_ctx}: confidence must be float in [0.0, 1.0]")
        if not run["input_hash"].startswith("sha256:"):
            raise ValidationError(f"{run_ctx}: input_hash must start with 'sha256:'")


def validate_embeddings(data: dict[str, Any], filename: str) -> None:
    """Validate any of the four *_embeddings.json files."""
    ctx = filename
    _require_schema_version(data, ctx)
    _require_keys(data, ["model_name", "model_version", "generated_at", "embeddings"], ctx)

    # Enforce model consistency
    if data["model_name"] != EMBEDDING_MODEL_NAME:
        raise ValidationError(
            f"{ctx}: model_name must be '{EMBEDDING_MODEL_NAME}', got '{data['model_name']}'. "
            "Regenerate all embeddings after a model upgrade."
        )
    if data["model_version"] != EMBEDDING_MODEL_VERSION:
        raise ValidationError(
            f"{ctx}: model_version mismatch: expected '{EMBEDDING_MODEL_VERSION}', "
            f"got '{data['model_version']}'. Run embedding_engine.py to regenerate."
        )

    _require_type(data["embeddings"], list, "embeddings", ctx)
    for i, emb in enumerate(data["embeddings"]):
        emb_ctx = f"{ctx}.embeddings[{i}]"
        _require_keys(emb, ["file_path", "hash", "chunk_index", "total_chunks", "embedding"], emb_ctx)
        if not isinstance(emb["embedding"], list) or len(emb["embedding"]) == 0:
            raise ValidationError(f"{emb_ctx}: embedding must be a non-empty list of floats")
        if len(emb["embedding"]) != EMBEDDING_DIM:
            raise ValidationError(
                f"{emb_ctx}: embedding dimension must be {EMBEDDING_DIM}, "
                f"got {len(emb['embedding'])}"
            )


# ---------------------------------------------------------------------------
# Dispatch table — maps filename to validator function
# ---------------------------------------------------------------------------
VALIDATORS: dict[str, Any] = {
    "repo_graph.json": validate_repo_graph,
    "module_map.json": validate_module_map,
    "dependency_graph.json": validate_dependency_graph,
    "infra_graph.json": validate_infra_graph,
    "ci_graph.json": validate_ci_graph,
    "decision_log.json": validate_decision_log,
    # Embeddings share the same validator, identifier passed as second arg
    "file_embeddings.json": lambda d: validate_embeddings(d, "file_embeddings.json"),
    "doc_embeddings.json": lambda d: validate_embeddings(d, "doc_embeddings.json"),
    "issue_embeddings.json": lambda d: validate_embeddings(d, "issue_embeddings.json"),
    "pr_embeddings.json": lambda d: validate_embeddings(d, "pr_embeddings.json"),
    "execution_log.json": validate_execution_log,
}


def validate_file(path: str) -> tuple[bool, str]:
    """
    Load and validate a single memory JSON file.

    Returns (passed: bool, error_message: str).
    """
    filename = os.path.basename(path)
    validator = VALIDATORS.get(filename)
    if validator is None:
        # Not a known memory file — skip without error
        return True, ""

    # Size check before loading
    try:
        file_size = os.path.getsize(path)
    except OSError as exc:
        return False, f"Cannot stat {path}: {exc}"

    size_limit = SIZE_LIMITS.get(filename)
    if size_limit and file_size > size_limit:
        return False, (
            f"{filename}: file size {file_size:,} bytes exceeds limit "
            f"{size_limit:,} bytes ({size_limit // (1024*1024)} MB)"
        )

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        return False, f"{filename}: invalid JSON — {exc}"
    except OSError as exc:
        return False, f"{filename}: cannot read — {exc}"

    try:
        validator(data)
    except ValidationError as exc:
        return False, str(exc)

    return True, ""


def load_json_safe(path: str) -> dict[str, Any] | None:
    """
    Load a JSON file safely, returning None on any error.
    Agents use this to avoid crashing when a memory file is absent or corrupted.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None
