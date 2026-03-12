# Contributing Guidelines

Thanks for contributing to **Terraform-Driven Ray on Kubernetes Platform**.

## Workflow

1. Pick an open issue or open a new one with clear reproduction steps or a concrete proposal.
2. Create a focused branch from `main`.
3. Run the local checks that match your change area.
4. Open a pull request with a Conventional Commit title and a short test plan.

## Local checks

- Infrastructure changes: `terraform validate`, `terraform test`, `opa test`
- Workload changes: `helm lint`, `helm template`, `kube-score`, Python compile for `workloads/` and `validation/`
- Automation changes: `pytest tests -q`

The repository `CI` workflow mirrors this split and only runs the relevant jobs for the changed paths.

## AI-assisted review

The supported AI surfaces are:

- `/gemini review`
- `/gemini summary`
- `@coderabbitai review`
- `@coderabbitai plan`
- `/plan` for linked task breakdowns on issues and discussions

The repository no longer uses custom Gemini CLI subagents or repo-hosted autonomous PR bots.

For the longer contributor guide, see [`docs/contributing.md`](docs/contributing.md).
