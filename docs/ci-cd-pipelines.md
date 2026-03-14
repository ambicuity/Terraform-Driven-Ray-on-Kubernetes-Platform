# CI/CD Pipelines

The repository uses one path-scoped CI workflow plus focused security/maintenance workflows.

## Required Checks

Branch protection requires:

- `CI Summary`
- `Secret Detection`
- `CodeQL Analyze (python)`

## Scoped CI Jobs

`ci.yml` routes work by path so infra and workload changes do not force unrelated validation:

- `terraform/**`, `policies/**` -> infra checks
- `helm/**`, `validation/**`, `workloads/**` -> workload checks
- `scripts/**`, `tests/**`, `.github/workflows/**` -> automation checks
- docs and repo guidance -> docs metadata checks

## What CI Validates

Infra:

- Terraform fmt / init / validate / test
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

## Advisory AI Surfaces

The repo keeps only advisory AI metadata and GitHub app integrations. There are no repo-owned autonomous issue/PR bots in the maintained workflow set.
