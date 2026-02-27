#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
test_repo_ingestion.py — Unit tests for repo_ingestion.py.

Tests structural ingestion functions with mocked filesystem data.
No actual repo files are required — all fixtures are created in tempfile.
"""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from repo_ingestion import (
    extract_python_imports,
    parse_terraform_file,
    parse_helm_chart,
    parse_ci_workflow,
    build_repo_graph,
    build_infra_graph,
    _file_type,
)


class TestExtractPythonImports(unittest.TestCase):

    def _write_py(self, tmpdir: str, name: str, content: str) -> str:
        path = os.path.join(tmpdir, name)
        with open(path, "w") as fh:
            fh.write(content)
        return path

    def test_simple_imports_extracted(self):
        """Top-level `import X` statements must be returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_py(tmpdir, "agent.py", "import os\nimport json\n")
            imports = extract_python_imports(path)
            self.assertIn("os", imports)
            self.assertIn("json", imports)

    def test_from_import_extracted(self):
        """from X import Y must return the top-level module X."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_py(tmpdir, "agent.py", "from gh_utils import GithubClient\n")
            imports = extract_python_imports(path)
            self.assertIn("gh_utils", imports)

    def test_dotted_module_trimmed_to_top_level(self):
        """from os.path import join must return 'os', not 'os.path'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_py(tmpdir, "agent.py", "from os.path import join\n")
            imports = extract_python_imports(path)
            self.assertIn("os", imports)
            self.assertNotIn("os.path", imports)

    def test_syntax_error_returns_empty(self):
        """A file with a syntax error must return [] without raising."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_py(tmpdir, "broken.py", "def broken(:\n    pass\n")
            imports = extract_python_imports(path)
            self.assertEqual(imports, [])

    def test_deduplication(self):
        """Duplicate imports must appear only once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_py(tmpdir, "agent.py", "import os\nimport os\n")
            imports = extract_python_imports(path)
            self.assertEqual(imports.count("os"), 1)


class TestParseTerraformFile(unittest.TestCase):

    def test_resource_extraction(self):
        """aws_eks_cluster resource must be returned with correct type and name."""
        tf_content = """
resource "aws_eks_cluster" "main" {
  name = "ray-cluster"
}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "main.tf")
            with open(path, "w") as fh:
                fh.write(tf_content)
            resources, modules, providers = parse_terraform_file(path)
            self.assertEqual(len(resources), 1)
            self.assertEqual(resources[0]["type"], "aws_eks_cluster")
            self.assertEqual(resources[0]["name"], "main")

    def test_provider_extraction(self):
        """provider blocks must be extracted as provider name strings."""
        tf_content = 'provider "aws" {\n  region = "us-east-1"\n}\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "versions.tf")
            with open(path, "w") as fh:
                fh.write(tf_content)
            _, _, providers = parse_terraform_file(path)
            self.assertIn("aws", providers)

    def test_empty_file_returns_empty(self):
        """An empty .tf file must return empty lists without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.tf")
            with open(path, "w") as fh:
                fh.write("")
            resources, modules, providers = parse_terraform_file(path)
            self.assertEqual(resources, [])
            self.assertEqual(modules, [])
            self.assertEqual(providers, [])

    def test_multiple_resources(self):
        """Multiple resource blocks must all be extracted."""
        tf_content = """
resource "aws_iam_role" "node_role" {}
resource "aws_security_group" "ray_sg" {}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "roles.tf")
            with open(path, "w") as fh:
                fh.write(tf_content)
            resources, _, _ = parse_terraform_file(path)
            self.assertEqual(len(resources), 2)
            types = {r["type"] for r in resources}
            self.assertIn("aws_iam_role", types)
            self.assertIn("aws_security_group", types)


class TestParseHelmChart(unittest.TestCase):

    def test_valid_chart_yaml(self):
        """A valid Chart.yaml must return chart name and version."""
        content = "apiVersion: v2\nname: ray\nversion: 1.2.3\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "Chart.yaml")
            with open(path, "w") as fh:
                fh.write(content)
            result = parse_helm_chart(path)
            self.assertIsNotNone(result)
            self.assertEqual(result["name"], "ray")
            self.assertEqual(result["version"], "1.2.3")

    def test_missing_name_returns_none(self):
        """A Chart.yaml without a name must return None."""
        content = "apiVersion: v2\nversion: 1.0.0\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "Chart.yaml")
            with open(path, "w") as fh:
                fh.write(content)
            result = parse_helm_chart(path)
            self.assertIsNone(result)


class TestParseCIWorkflow(unittest.TestCase):

    def test_trigger_extraction(self):
        """Workflow trigger events must be extracted correctly."""
        content = (
            "name: Agent Delta\non:\n  issues:\n    types: [labeled]\n"
            "jobs:\n  execute:\n    runs-on: ubuntu-latest\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "delta.yml")
            with open(path, "w") as fh:
                fh.write(content)
            result = parse_ci_workflow(path)
            self.assertIsNotNone(result)
            self.assertIn("issues", result["triggers"])

    def test_script_reference_extraction(self):
        """python scripts/X.py references in 'run:' must be captured."""
        content = (
            "name: Test\non:\n  push:\njobs:\n  run:\n    steps:\n"
            "      - run: python scripts/delta_executor.py\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.yml")
            with open(path, "w") as fh:
                fh.write(content)
            result = parse_ci_workflow(path)
            self.assertIn("scripts/delta_executor.py", result["depends_on_scripts"])


class TestFileType(unittest.TestCase):

    def test_python_extension(self):
        self.assertEqual(_file_type("scripts/agent.py"), "python")

    def test_terraform_extension(self):
        self.assertEqual(_file_type("terraform/main.tf"), "terraform")

    def test_rego_extension(self):
        self.assertEqual(_file_type("policies/allow.rego"), "rego")

    def test_yml_extension(self):
        self.assertEqual(_file_type(".github/workflows/foo.yml"), "yaml")

    def test_unknown_extension(self):
        self.assertEqual(_file_type("Makefile"), "other")


class TestBuildRepoGraph(unittest.TestCase):

    def test_graph_built_from_real_scripts_dir(self):
        """Build repo graph against the actual scripts/ directory and validate output."""
        nodes, edges, metrics = build_repo_graph(REPO_ROOT)
        # Must have found at least our new memory scripts
        py_nodes = [n for n in nodes if n["type"] == "python"]
        self.assertGreater(len(py_nodes), 5, "Expected to find Python files in the repo")
        # Metrics must be non-zero
        self.assertGreater(metrics["total_files"], 0)
        self.assertGreater(metrics["python_files"], 0)
        # gh_utils → memory_schemas import edge must exist
        edge_froms = {e["from"] for e in edges}
        self.assertTrue(
            any("scripts/" in f for f in edge_froms),
            "Expected import edges from scripts/ directory"
        )

    def test_excluded_dirs_not_in_nodes(self):
        """Excluded directories (.git, __pycache__, .venv) must not appear in nodes."""
        nodes, _, _ = build_repo_graph(REPO_ROOT)
        for node in nodes:
            for excluded in (".git/", "__pycache__/", ".venv/", ".memory/"):
                self.assertFalse(
                    node["path"].startswith(excluded),
                    f"Excluded path leaked into nodes: {node['path']}"
                )


if __name__ == "__main__":
    unittest.main()
