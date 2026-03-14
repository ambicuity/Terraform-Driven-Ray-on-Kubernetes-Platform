# CI/CD Pipelines

The repository uses one path-scoped CI workflow plus focused security and maintenance workflows.

## Required Checks

Branch protection requires:

- `CI Summary`
- `Secret Detection`
- `CodeQL Analyze (python)`

`CI Summary` is the single required gate from [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## Scoped CI Jobs

`ci.yml` routes work by path so infra and workload changes do not force unrelated validation:

| Changed paths | Job |
|---|---|
| `terraform/**`, `policies/**` | `infra-ci` |
| `helm/**`, `workloads/**`, `validation/**` | `app-ci` |
| `scripts/**`, `tests/**`, `.github/workflows/**` | `automation-ci` |
| `README.md`, `docs/**`, repo guidance | `docs-meta` |

`CI Summary` always runs, even if scoped jobs are skipped.

## What CI Validates

Infra:

- Terraform fmt, init, validate, and test
- example stack validate
- TFLint
- Checkov
- OPA policy tests

Workloads:

- Python `compileall`
- `helm lint`
- `helm template`

Automation:

- `actionlint`
- `pytest tests -q`
- Python `compileall` for `scripts/` and `tests/`
- docs metadata checks that reject stale workflow and legacy AI-runtime references

## Additional Workflows

| Workflow | Trigger | Notes |
|---|---|---|
| `codeql.yml` | PR, push, schedule | semantic analysis |
| `gitleaks.yml` | PR, push | secret scanning |
| `drift-detection.yml` | schedule, manual | Terraform drift detection via AWS OIDC |
| `stale.yml` | schedule, manual | stale issue and PR management |
| `assignment-followup.yml` | schedule, manual | nudges assigned issues without linked open PRs |

## Advisory AI Surfaces

The repo keeps only advisory AI metadata and GitHub app integrations. CodeRabbit, Gemini Code Assist on GitHub, and official GitHub Agentic Workflows are optional helpers, not merge gates, and there are no repo-owned autonomous issue or PR bots in the maintained workflow set.
