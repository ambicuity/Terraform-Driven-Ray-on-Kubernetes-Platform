# Contributing Guidelines

Thanks for contributing to **Terraform-Driven Ray on Kubernetes Platform**.

## Workflow

1. Pick an open issue or open a new one with clear reproduction steps or a concrete proposal.
2. Create a focused branch from `main`.
3. Run the local checks that match your change area.
4. Open a pull request with a Conventional Commit title and a short test plan.

## Local checks

- Infrastructure changes: `terraform -chdir=terraform init -backend=false`, `terraform -chdir=terraform validate`, `terraform -chdir=terraform test`, `opa test policies -v`
- Workload changes: `python -m compileall workloads validation`, `helm lint helm/ray`, `helm template ray-ci helm/ray >/tmp/ray-rendered.yaml`, `kube-score score /tmp/ray-rendered.yaml --ignore-test container-security-context-privileged --output-format ci`
- Automation changes: `python -m compileall scripts tests`, `pytest tests -q`
- Workflow changes: `actionlint`

The repository `CI` workflow mirrors this split and only runs the relevant jobs for the changed paths.

## Optional review tools

CodeRabbit and Gemini Code Assist on GitHub are available if you want advisory feedback, but they are optional and not part of the merge gate.

For the longer contributor guide, see [`docs/contributing.md`](docs/contributing.md).
