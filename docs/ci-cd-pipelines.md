# CI/CD Pipelines

This repository keeps one path-scoped CI workflow and a small set of focused security and maintenance workflows.

## Required checks on `main`

The ruleset in the repo root requires these checks:

- `CI Summary`
- `Secret Detection`
- `CodeQL Analyze (python)`

`CI Summary` is the single required CI gate from [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## Why the repo uses a router

The repository contains Terraform, Helm workloads, Python automation, OPA policies, and docs in one place. The router keeps docs-only and automation-only changes from paying the full infrastructure validation cost.

## Path map

| Changed paths | Job |
|---|---|
| `terraform/**`, `policies/**` | `infra-ci` |
| `helm/**`, `workloads/**`, `validation/**` | `app-ci` |
| `scripts/**`, `tests/**`, `.github/workflows/**` | `automation-ci` |
| `README.md`, `docs/**`, `DEPLOYMENT.md`, templates, and repo docs | `docs-meta` |

`CI Summary` always runs, even when scoped jobs are skipped.

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
- `actionlint`
- `pytest tests -q`

### `docs-meta`

- rejects references to removed AI workflow files and disabled GitHub-side agent workflows
- rejects stale instructions for removed commands and secrets
- rejects unpinned GitHub Terraform module source strings in docs

## Additional workflows

| Workflow | Trigger | Notes |
|---|---|---|
| `codeql.yml` | PR, push, schedule | semantic code analysis |
| `gitleaks.yml` | PR, push | secret scanning |
| `drift-detection.yml` | weekly, manual | skips cleanly unless AWS OIDC secrets are configured |
| `release-drafter.yml` | push to `main`, manual | draft release notes |
| `stale.yml` | weekly, manual | low-noise stale issue and PR handling |
| `contributor-greeting.yml` | first issue or PR | points contributors to local checks and docs |

## Advisory review tools

CodeRabbit and Gemini Code Assist on GitHub are optional review tools. They are not required for contributors and they are not part of branch protection.
