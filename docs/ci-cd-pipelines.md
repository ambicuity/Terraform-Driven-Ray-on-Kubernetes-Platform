# CI/CD Pipelines

This repository keeps one required CI workflow and a small number of focused security and maintenance workflows.

## Required CI gate

`CI` in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) is the required branch-protection check.

### Why the repo uses a router

The repository contains Terraform, Helm workloads, Python automation, OPA policies, and docs in one place. A single unscoped CI workflow makes every change pay the full infra and workload validation cost. The current router limits that blast radius by running only the jobs relevant to the changed paths.

### Path map

| Changed paths | Job |
|---|---|
| `terraform/**`, `policies/**` | `infra-ci` |
| `helm/**`, `workloads/**`, `validation/**` | `app-ci` |
| `scripts/**`, `tests/**`, `.github/workflows/**`, `.gemini/**`, `.coderabbit.yaml` | `automation-ci` |
| `README.md`, `docs/**`, contribution/security templates | `docs-meta` |

`CI Summary` always runs, even if the scoped jobs are skipped.

## What each CI job does

### `infra-ci`

- `terraform fmt -check -recursive terraform/`
- `terraform init` and `terraform validate` for the root module
- `terraform init` and `terraform validate` for `terraform/examples/complete`
- `terraform test`
- `tflint`
- `checkov`
- `opa test`

### `app-ci`

- `python -m compileall workloads validation`
- `helm lint helm/ray`
- `helm template helm/ray`
- `kube-score`

### `automation-ci`

- `python -m compileall scripts tests`
- `pytest tests -q`

### `docs-meta`

- rejects stale references to removed workflows and legacy AI runtime files
- rejects unpinned GitHub Terraform module source strings in docs

## Additional workflows

| Workflow | Trigger | Notes |
|---|---|---|
| `codeql.yml` | PR, push, schedule | dedicated semantic analysis |
| `gitleaks.yml` | PR, push | dedicated secret scanning |
| `drift-detection.yml` | schedule, manual | Terraform drift detection via AWS OIDC |
| `release-drafter.yml` | push to `main`, manual | draft release notes |
| `stale.yml` | schedule, manual | stale issue and PR management |
| `assignment-followup.yml` | schedule, manual | only nudges assigned issues without linked open PRs |

## AI and advisory workflows

Official GitHub Agentic Workflows, CodeRabbit, and Gemini Code Assist are advisory. They help with triage, planning, reviews, and reporting, but they are not the merge gate.

See [GitHub Automation](ai-automation.md) for the supported AI surfaces and commands.
