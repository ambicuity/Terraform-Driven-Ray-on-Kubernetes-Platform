# GitHub Automation

This repository keeps GitHub automation intentionally small. The merge gate is deterministic, while AI review tools remain optional.

## Required merge checks

- `CI Summary`
- `Secret Detection`
- `CodeQL Analyze (python)`

These checks are enforced through the repository ruleset, not through advisory AI tooling.

## Optional review tools

| Surface | Purpose | Trigger |
|---|---|---|
| CodeRabbit | Advisory PR review and planning help | `@coderabbitai review`, `@coderabbitai full review`, `@coderabbitai plan` |
| Gemini Code Assist on GitHub | Advisory PR summary and review | `/gemini summary`, `/gemini review` |

These tools are optional for contributors and do not need repository secrets.

## Disabled repo-managed AI automation

The repository does not use repo-owned AI workflows for planning, triage, CI diagnosis, or autonomous issue management.

Additional GitHub-side agent workflows beyond CodeRabbit and Gemini are disabled by project policy and are not part of repository operations.

## Deterministic workflows that remain

| Workflow | Purpose |
|---|---|
| `ci.yml` | Path-scoped required CI gate |
| `codeql.yml` | CodeQL analysis |
| `gitleaks.yml` | Secret scanning |
| `drift-detection.yml` | Optional scheduled Terraform drift detection using AWS OIDC |
| `contributor-greeting.yml` | Welcome first-time issue and PR authors |
| `stale.yml` | Low-noise stale issue and PR management |
| `release-drafter.yml` | Draft release notes on `main` |

## Repository secrets still in use

- `AWS_ROLE_ARN` and `AWS_REGION` for optional drift detection
- Standard short-lived `GITHUB_TOKEN` for normal workflow execution
