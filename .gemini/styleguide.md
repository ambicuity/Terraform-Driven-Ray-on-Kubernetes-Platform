# Gemini Review Style Guide

Review this repository as a production EKS and Ray platform with mixed infrastructure and workload content.

## Focus Areas

- Prioritize correctness, operational safety, and blast radius over style.
- Treat Terraform, Helm, OPA, Python automation, and GitHub workflows as different risk domains with different validation needs.
- Call out any change that makes CI less path-scoped or expands infra validation onto unrelated app, docs, or automation changes.

## Terraform

- Require pinned Terraform module sources when consuming this repository from GitHub.
- Flag IAM overreach, missing encryption, drift-prone resources, and unnecessary coupling between infra and workload delivery.
- Prefer OIDC and IRSA over static credentials.

## Helm and Ray

- Look for missing probes, weak disruption handling, absent requests or limits, and unclear scheduling intent.
- Call out workload changes that bypass the documented validation flow (`helm lint`, `helm template`, `kube-score`).

## Python and Workflows

- Prefer deterministic scripts with explicit error handling.
- Flag references to deleted AI runtime components such as Gemini CLI subagents, queue files, hidden memory stores, or deprecated labels.
- Keep AI apps advisory. Deterministic GitHub Actions should remain the merge gate.
