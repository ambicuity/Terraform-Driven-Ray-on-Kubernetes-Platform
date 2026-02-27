#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
repo_ingestion.py — Repository Deep Ingestion Engine.

Walks the repository tree and builds five structural memory artifacts:
  - repo_graph.json       : file nodes + import/dependency edges
  - module_map.json       : component boundaries and ownership
  - dependency_graph.json : cross-file dependency depth
  - infra_graph.json      : Terraform resources, Helm charts
  - ci_graph.json         : GitHub Actions workflow triggers and step graph

All artifacts are written to .memory/ as deterministic, schema-validated JSON.
This script requires Python 3.11 stdlib only (no third-party packages).

Usage:
  python scripts/repo_ingestion.py [--repo-root REPO_ROOT] [--output-dir OUTPUT_DIR]

Environment variables (optional — used for GitHub API calls):
  GITHUB_TOKEN        : For fetching issue/PR metadata
  GITHUB_REPOSITORY   : owner/repo string (e.g. ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform)
"""

import argparse
import ast
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

# Ensure scripts/ is on the path so we can import memory_schemas
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from memory_schemas import (
    SCHEMA_VERSION,
    validate_repo_graph,
    validate_module_map,
    validate_dependency_graph,
    validate_infra_graph,
    validate_ci_graph,
    ValidationError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("repo_ingestion")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# File extensions that contribute to repo memory
INDEXED_EXTENSIONS = frozenset([
    ".py", ".tf", ".rego", ".yml", ".yaml", ".md", ".json", ".hcl", ".sh",
])
# Directories to exclude from walking (noise, generated, VCS)
EXCLUDED_DIRS = frozenset([
    ".git", ".venv", ".venv-ray-test", "__pycache__", ".pytest_cache",
    ".terraform", "node_modules", ".memory",
])
# Terraform resource/module patterns
_TF_RESOURCE_RE = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"', re.MULTILINE)
_TF_MODULE_RE = re.compile(r'^module\s+"([^"]+)"\s*\{.*?source\s*=\s*"([^"]+)"', re.MULTILINE | re.DOTALL)
_TF_PROVIDER_RE = re.compile(r'^provider\s+"([^"]+)"', re.MULTILINE)
# Helm Chart.yaml version pattern
_HELM_VERSION_RE = re.compile(r'^version:\s*(.+)', re.MULTILINE)
_HELM_NAME_RE = re.compile(r'^name:\s*(.+)', re.MULTILINE)
# CI workflow trigger patterns
_YML_ON_RE = re.compile(r'^on:\s*$', re.MULTILINE)


def _sha256_file(path: str) -> str:
    """Compute SHA-256 hex digest of a file's content."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError as exc:
        logger.warning("Cannot hash %s: %s", path, exc)
        return "sha256:error"
    return f"sha256:{h.hexdigest()}"


def _file_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".py": "python", ".tf": "terraform", ".hcl": "terraform",
        ".rego": "rego", ".yml": "yaml", ".yaml": "yaml",
        ".md": "markdown", ".json": "json", ".sh": "shell",
    }.get(ext, "other")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Python import extraction (AST-based — deterministic, does not exec code)
# ---------------------------------------------------------------------------

def extract_python_imports(path: str) -> list[str]:
    """Return a list of top-level module names imported by a Python file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=path)
    except (SyntaxError, OSError) as exc:
        logger.debug("Cannot parse %s: %s", path, exc)
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return list(dict.fromkeys(imports))  # deduplicate, preserve order


# ---------------------------------------------------------------------------
# Terraform parsing
# ---------------------------------------------------------------------------

def parse_terraform_file(path: str) -> tuple[list[dict], list[dict], list[str]]:
    """
    Parse a .tf file and return (resources, modules, providers).
    All parsing uses regex — no HCL parser required.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return [], [], []

    resources = [
        {"type": m.group(1), "name": m.group(2), "file": path, "depends_on": []}
        for m in _TF_RESOURCE_RE.finditer(content)
    ]
    modules = [
        {"name": m.group(1), "source": m.group(2), "file": path}
        for m in _TF_MODULE_RE.finditer(content)
    ]
    providers = [m.group(1) for m in _TF_PROVIDER_RE.finditer(content)]
    return resources, modules, providers


# ---------------------------------------------------------------------------
# Helm chart parsing
# ---------------------------------------------------------------------------

def parse_helm_chart(chart_yaml_path: str) -> dict[str, Any] | None:
    """Parse a Helm Chart.yaml (simple key:value lines — no YAML lib needed)."""
    try:
        with open(chart_yaml_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return None

    name_match = _HELM_NAME_RE.search(content)
    version_match = _HELM_VERSION_RE.search(content)
    if not name_match:
        return None

    return {
        "name": name_match.group(1).strip(),
        "path": os.path.dirname(chart_yaml_path),
        "version": version_match.group(1).strip() if version_match else "unknown",
        "dependencies": [],
    }


# ---------------------------------------------------------------------------
# CI workflow parsing
# ---------------------------------------------------------------------------

def parse_ci_workflow(path: str) -> dict[str, Any] | None:
    """
    Parse a GitHub Actions workflow YAML file using line-by-line analysis.
    Extracts: name, triggers, jobs, and scripts referenced.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    name = os.path.splitext(os.path.basename(path))[0]
    triggers: list[str] = []
    jobs: list[str] = []
    scripts: list[str] = []
    permissions: dict[str, str] = {}

    in_on_block = False
    in_permissions = False
    for line in lines:
        stripped = line.strip()
        # Workflow display name
        if stripped.startswith("name:") and not triggers and not jobs:
            name = stripped[5:].strip().strip("'\"") or name

        # Trigger block detection
        if stripped == "on:":
            in_on_block = True
            in_permissions = False
            continue
        if stripped == "permissions:":
            in_on_block = False
            in_permissions = True
            continue
        if stripped == "jobs:":
            in_on_block = False
            in_permissions = False
            continue

        if in_on_block and stripped and not stripped.startswith("#"):
            # Each non-empty line under `on:` is a trigger event
            trigger_key = stripped.rstrip(":").rstrip()
            if trigger_key and not trigger_key.startswith("-"):
                triggers.append(trigger_key)

        if in_permissions and ":" in stripped:
            perm_key, _, perm_val = stripped.partition(":")
            permissions[perm_key.strip()] = perm_val.strip()

        # Job names (lines like "  job-name:")
        job_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if job_match and "steps" not in stripped:
            jobs.append(job_match.group(1))

        # Script references in run: python scripts/...
        script_match = re.search(r"python\s+(scripts/[^\s]+\.py)", stripped)
        if script_match:
            scripts.append(script_match.group(1))

    return {
        "name": name,
        "path": path,
        "triggers": triggers,
        "jobs": jobs,
        "depends_on_scripts": scripts,
        "permissions": permissions,
    }


# ---------------------------------------------------------------------------
# Main ingestion runner
# ---------------------------------------------------------------------------

def build_repo_graph(repo_root: str) -> tuple[list[dict], list[dict], dict]:
    """Walk repo and build node list and import edges."""
    nodes: list[dict] = []
    edges: list[dict] = []

    # We need a map from module name → file path for edge building
    py_filemap: dict[str, str] = {}  # stem → relative path

    all_py_files: list[str] = []

    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Prune excluded directories in-place (affects os.walk recursion)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in INDEXED_EXTENSIONS:
                continue

            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, repo_root)
            file_size = 0
            try:
                file_size = os.path.getsize(abs_path)
            except OSError:
                pass

            ftype = _file_type(abs_path)
            node: dict[str, Any] = {
                "path": rel_path,
                "type": ftype,
                "size_bytes": file_size,
                "hash": _sha256_file(abs_path),
            }
            nodes.append(node)

            if ftype == "python":
                stem = os.path.splitext(fname)[0]
                py_filemap[stem] = rel_path
                all_py_files.append(abs_path)

    # Build import edges for Python files
    for abs_path in all_py_files:
        rel_path = os.path.relpath(abs_path, repo_root)
        for mod_name in extract_python_imports(abs_path):
            if mod_name in py_filemap:
                edges.append({
                    "from": rel_path,
                    "to": py_filemap[mod_name],
                    "relation": "imports",
                })

    # Count by type
    type_counts: dict[str, int] = {}
    for node in nodes:
        type_counts[node["type"]] = type_counts.get(node["type"], 0) + 1

    metrics = {
        "total_files": len(nodes),
        "python_files": type_counts.get("python", 0),
        "terraform_files": type_counts.get("terraform", 0),
        "helm_files": type_counts.get("yaml", 0),
        "markdown_files": type_counts.get("markdown", 0),
    }
    return nodes, edges, metrics


def build_module_map(repo_root: str, nodes: list[dict]) -> list[dict]:
    """Identify component boundaries and group files into modules."""
    modules: list[dict] = []
    # Group files by their top-level directory
    dir_groups: dict[str, list[str]] = {}
    for node in nodes:
        parts = node["path"].split(os.sep)
        top_dir = parts[0] if len(parts) > 1 else "root"
        dir_groups.setdefault(top_dir, []).append(node["path"])

    type_map = {
        "scripts": "python_package",
        "tests": "python_package",
        "terraform": "terraform_module",
        "helm": "helm_chart",
        "policies": "rego_policy",
        ".github": "ci_workflow",
        "docs": "docs",
        "workloads": "yaml",
        "monitoring": "yaml",
        "validation": "yaml",
        "diagrams": "docs",
    }

    for dir_name, files in dir_groups.items():
        mod_type = type_map.get(dir_name, "docs")
        # Identify exported symbols for python packages
        exports: list[str] = []
        if mod_type == "python_package":
            for f in files:
                if f.endswith(".py"):
                    abs_path = os.path.join(repo_root, f)
                    try:
                        with open(abs_path, encoding="utf-8", errors="replace") as fh:
                            src = fh.read()
                        tree = ast.parse(src)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                if not node.name.startswith("_"):
                                    exports.append(node.name)
                    except (SyntaxError, OSError):
                        pass

        modules.append({
            "name": dir_name,
            "path": dir_name,
            "type": mod_type,
            "files": sorted(files),
            "description": f"Component: {dir_name}",
            "dependencies": [],
            "exports": exports[:50],  # cap to avoid bloat
        })

    return modules


def build_dependency_graph(edges: list[dict]) -> list[dict]:
    """Build dependency records with depth from raw import edges."""
    deps: list[dict] = []
    for edge in edges:
        deps.append({
            "source": edge["from"],
            "target": edge["to"],
            "type": "direct_import",
            "depth": 1,
        })
    return deps


def build_infra_graph(repo_root: str) -> dict[str, Any]:
    """Parse all .tf files and Helm charts into infra_graph."""
    all_resources: list[dict] = []
    all_modules: list[dict] = []
    all_providers: list[str] = []
    helm_charts: list[dict] = []

    # Terraform
    tf_dir = os.path.join(repo_root, "terraform")
    if os.path.isdir(tf_dir):
        for dirpath, dirnames, filenames in os.walk(tf_dir):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for fname in filenames:
                if fname.endswith((".tf", ".hcl")):
                    abs_path = os.path.join(dirpath, fname)
                    resources, modules, providers = parse_terraform_file(abs_path)
                    all_resources.extend(resources)
                    all_modules.extend(modules)
                    all_providers.extend(providers)

    # Helm — find all Chart.yaml files
    helm_dir = os.path.join(repo_root, "helm")
    if os.path.isdir(helm_dir):
        for dirpath, _, filenames in os.walk(helm_dir):
            for fname in filenames:
                if fname == "Chart.yaml":
                    chart = parse_helm_chart(os.path.join(dirpath, fname))
                    if chart:
                        helm_charts.append(chart)

    return {
        "terraform": {
            "resources": all_resources,
            "modules": all_modules,
            "providers": list(dict.fromkeys(all_providers)),
        },
        "helm": {
            "charts": helm_charts,
        },
    }


def build_ci_graph(repo_root: str) -> tuple[list[dict], list[dict]]:
    """Parse all .github/workflows/*.yml files into workflow metadata."""
    workflows: list[dict] = []
    workflow_dir = os.path.join(repo_root, ".github", "workflows")
    if not os.path.isdir(workflow_dir):
        return [], []

    for fname in sorted(os.listdir(workflow_dir)):
        if not fname.endswith((".yml", ".yaml")):
            continue
        abs_path = os.path.join(workflow_dir, fname)
        wf = parse_ci_workflow(abs_path)
        if wf:
            workflows.append(wf)

    return workflows, []  # failure_history starts empty; updated by CI runs


def write_json(data: dict, path: str) -> None:
    """Write dict as formatted JSON, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    logger.info("Written: %s (%d bytes)", path, os.path.getsize(path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Repository structural ingestion engine")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--output-dir", default=".memory", help="Output directory for memory artifacts")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    output_dir = os.path.abspath(args.output_dir)
    now = _now_iso()

    logger.info("Starting repo ingestion: root=%s output=%s", repo_root, output_dir)

    # --- Repo graph ---
    logger.info("Building repo graph...")
    nodes, edges, metrics = build_repo_graph(repo_root)
    repo_graph: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "nodes": nodes,
        "edges": edges,
        "metrics": metrics,
    }
    try:
        validate_repo_graph(repo_graph)
    except ValidationError as exc:
        logger.error("repo_graph validation failed: %s", exc)
        sys.exit(1)
    write_json(repo_graph, os.path.join(output_dir, "repo_graph.json"))

    # --- Module map ---
    logger.info("Building module map...")
    modules = build_module_map(repo_root, nodes)
    module_map: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "modules": modules,
    }
    try:
        validate_module_map(module_map)
    except ValidationError as exc:
        logger.error("module_map validation failed: %s", exc)
        sys.exit(1)
    write_json(module_map, os.path.join(output_dir, "module_map.json"))

    # --- Dependency graph ---
    logger.info("Building dependency graph...")
    deps = build_dependency_graph(edges)
    dep_graph: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "dependencies": deps,
    }
    try:
        validate_dependency_graph(dep_graph)
    except ValidationError as exc:
        logger.error("dependency_graph validation failed: %s", exc)
        sys.exit(1)
    write_json(dep_graph, os.path.join(output_dir, "dependency_graph.json"))

    # --- Infra graph ---
    logger.info("Building infra graph...")
    infra_data = build_infra_graph(repo_root)
    infra_graph: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        **infra_data,
    }
    try:
        validate_infra_graph(infra_graph)
    except ValidationError as exc:
        logger.error("infra_graph validation failed: %s", exc)
        sys.exit(1)
    write_json(infra_graph, os.path.join(output_dir, "infra_graph.json"))

    # --- CI graph ---
    logger.info("Building CI graph...")
    wf_list, fail_hist = build_ci_graph(repo_root)
    ci_graph: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "workflows": wf_list,
        "failure_history": fail_hist,
    }
    try:
        validate_ci_graph(ci_graph)
    except ValidationError as exc:
        logger.error("ci_graph validation failed: %s", exc)
        sys.exit(1)
    write_json(ci_graph, os.path.join(output_dir, "ci_graph.json"))

    logger.info(
        "Ingestion complete. Files: %d, Edges: %d, Modules: %d, TF resources: %d, Workflows: %d",
        len(nodes), len(edges), len(modules),
        len(infra_graph["terraform"]["resources"]), len(wf_list),
    )


if __name__ == "__main__":
    main()
