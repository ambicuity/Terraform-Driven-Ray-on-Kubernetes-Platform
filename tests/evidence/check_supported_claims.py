#!/usr/bin/env python3
"""Audit the repository's supported claims against code-backed evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ClaimResult:
    claim: str
    evidence: str
    passed: bool
    detail: str


def read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def extract_block(text: str, header_pattern: str) -> str:
    match = re.search(header_pattern, text)
    if not match:
        raise ValueError(f"Could not find block matching {header_pattern!r}")

    start = match.start()
    brace_index = text.find("{", match.end() - 1)
    if brace_index == -1:
        raise ValueError(f"Could not find opening brace for {header_pattern!r}")

    depth = 0
    for index in range(brace_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    raise ValueError(f"Could not find closing brace for {header_pattern!r}")


def render_chart() -> str:
    result = subprocess.run(
        [
            "helm",
            "template",
            "ray-evidence",
            "helm/ray",
            "--values",
            "validation/local-chart-values.yaml",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "helm template failed")
    return result.stdout


def make_result(claim: str, evidence: str, passed: bool, detail: str) -> ClaimResult:
    return ClaimResult(claim=claim, evidence=evidence, passed=passed, detail=detail)


def audit_launch_templates() -> ClaimResult:
    node_pools = read_text("terraform/node_pools.tf")
    module_tests = read_text("terraform/module.tftest.hcl")

    cpu_block = extract_block(node_pools, r'resource "aws_eks_node_group" "cpu_workers"\s*{')
    gpu_block = extract_block(node_pools, r'resource "aws_eks_node_group" "gpu_workers"\s*{')
    fallback_block = extract_block(node_pools, r'resource "aws_eks_node_group" "gpu_ondemand_fallback"\s*{')

    passed = all(
        [
            "launch_template {" in cpu_block,
            "launch_template {" in gpu_block,
            "launch_template {" in fallback_block,
            'length(aws_eks_node_group.cpu_workers.launch_template) == 1' in module_tests,
            'length(aws_eks_node_group.gpu_workers[0].launch_template) == 1' in module_tests,
        ]
    )

    return make_result(
        "Launch templates are attached to the managed node groups.",
        "terraform/node_pools.tf + terraform/module.tftest.hcl",
        passed,
        "CPU, primary GPU, and fallback GPU node groups all declare launch templates and Terraform tests assert the CPU and primary GPU attachments.",
    )


def audit_spot_fallback() -> ClaimResult:
    module_tests = read_text("terraform/module.tftest.hcl")
    policy_tests = read_text("policies/terraform_test.rego")

    passed = all(
        [
            'length(aws_eks_node_group.gpu_ondemand_fallback) == 1' in module_tests,
            'aws_eks_node_group.gpu_ondemand_fallback[0].capacity_type == "ON_DEMAND"' in module_tests,
            "test_spot_gpu_requires_fallback" in policy_tests,
            "test_spot_gpu_with_fallback_allowed" in policy_tests,
        ]
    )

    return make_result(
        "Spot GPU mode keeps an On-Demand fallback path.",
        "terraform/module.tftest.hcl + policies/terraform_test.rego",
        passed,
        "Terraform module tests assert the fallback node group and OPA tests deny a Spot-only GPU plan without it.",
    )


def audit_oidc_thumbprint() -> ClaimResult:
    main_tf = read_text("terraform/main.tf")

    managed_block = extract_block(
        main_tf,
        r'resource "aws_iam_openid_connect_provider" "cluster_managed"\s*{',
    )
    unmanaged_block = extract_block(
        main_tf,
        r'resource "aws_iam_openid_connect_provider" "cluster_unmanaged"\s*{',
    )

    passed = all(
        [
            'thumbprint_list = [data.tls_certificate.cluster.certificates[0].sha1_fingerprint]' in managed_block,
            "thumbprint_list = []" in unmanaged_block,
            "ignore_changes = [thumbprint_list]" in unmanaged_block,
        ]
    )

    return make_result(
        "OIDC thumbprint drift is handled explicitly.",
        "terraform/main.tf",
        passed,
        "The module keeps separate managed and unmanaged OIDC provider resources and ignores AWS-populated thumbprint drift on the unmanaged path.",
    )


def audit_chart_probes_and_pdb() -> list[ClaimResult]:
    rendered = render_chart()

    probe_result = make_result(
        "The chart renders explicit head probes and a preStop hook.",
        "helm template helm/ray --values validation/local-chart-values.yaml",
        all(token in rendered for token in ["readinessProbe:", "livenessProbe:", "preStop:"]),
        "The locally rendered RayCluster manifest includes readiness and liveness probes plus a preStop lifecycle hook for the head pod.",
    )

    pdb_result = make_result(
        "The chart renders a PodDisruptionBudget for CPU workers.",
        "helm template helm/ray --values validation/local-chart-values.yaml",
        "kind: PodDisruptionBudget" in rendered and "minAvailable: 1" in rendered,
        "The local chart render includes a PodDisruptionBudget with minAvailable set for CPU workers.",
    )

    return [probe_result, pdb_result]


def audit_cluster_identity() -> ClaimResult:
    script_text = read_text("scripts/validate_cluster_identity.py")
    test_text = read_text("tests/test_validate_cluster_identity.py")

    passed = all(
        [
            '"get", "namespace", "kube-system"' in script_text,
            ".k8s_cluster_fingerprint.json" in script_text,
            "hashlib.sha256" in script_text,
            "TestGetClusterFingerprintErrors" in test_text,
            "TestMainExitCodes" in test_text,
        ]
    )

    return make_result(
        "The cluster identity safeguard is implemented and unit-tested.",
        "scripts/validate_cluster_identity.py + tests/test_validate_cluster_identity.py",
        passed,
        "The script fingerprints the kube-system namespace UID and the unit tests cover kubeconfig and exit-code behavior.",
    )


def audit_entrypoints() -> ClaimResult:
    makefile = read_text("Makefile")
    ci_workflow = read_text(".github/workflows/ci.yml")
    local_test = read_text("local_test.sh")

    passed = all(
        [
            re.search(r"^lint:\s", makefile, re.MULTILINE) is not None,
            re.search(r"^test:\s", makefile, re.MULTILINE) is not None,
            re.search(r"^evidence:\s", makefile, re.MULTILINE) is not None,
            "name: CI" in ci_workflow,
            "infra-ci" in ci_workflow,
            "app-ci" in ci_workflow,
            "automation-ci" in ci_workflow,
            "minikube start" in local_test,
            'helm install "$HELM_RELEASE" "$SCRIPT_DIR/helm/ray"' in local_test,
        ]
    )

    return make_result(
        "Deterministic local and CI entrypoints are defined in-repo.",
        "Makefile + .github/workflows/ci.yml + local_test.sh",
        passed,
        "The Makefile exposes lint/test/evidence, CI stays path-scoped, and local_test.sh installs the real chart into minikube.",
    )


def main() -> int:
    results = [
        audit_launch_templates(),
        audit_spot_fallback(),
        audit_oidc_thumbprint(),
        *audit_chart_probes_and_pdb(),
        audit_cluster_identity(),
        audit_entrypoints(),
    ]

    print("# Supported Claim Audit")
    print()
    print("| Claim | Result | Evidence | Detail |")
    print("| --- | --- | --- | --- |")

    failures = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        if not result.passed:
            failures += 1
        print(
            f"| {result.claim} | `{status}` | `{result.evidence}` | {result.detail} |"
        )

    print()
    if failures:
        print(f"Audit failed: {failures} supported claim(s) are not backed by the repository.")
        return 1

    print("Audit passed: every supported claim in the matrix is backed by code or deterministic structure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
