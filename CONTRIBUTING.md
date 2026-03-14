# Contributing Guidelines

Thanks for contributing to **Terraform-Driven Ray on Kubernetes Platform**.

## Workflow

1. Pick an open issue or open a new one with clear reproduction steps or a concrete proposal.
2. Create a focused branch from `main`.
3. Run the local checks that match your change area.
4. Open a pull request with a Conventional Commit title and a short test plan.

## Local checks

- Preferred: `make lint` and `make test`
- Infrastructure changes: `./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform init -backend=false`, `./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform validate`, `./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform test`, `./.tmp-tools/bin/opa-0.63.0 test policies -v`
- Workload changes: `python3 -m compileall workloads validation`, `helm lint helm/ray`, `helm template ray-ci helm/ray >/tmp/ray-rendered.yaml`
- Automation changes: `python3 -m compileall scripts tests`, `pytest tests -q`
- Workflow and shell changes: `actionlint`, `shellcheck local_test.sh validation/*.sh`

The repository `CI` workflow mirrors this split and only runs the relevant jobs for the changed paths.

## Optional review tools

CodeRabbit and Gemini Code Assist on GitHub are available if you want advisory feedback, but they are optional and not part of the merge gate.

For the longer contributor guide, see [`docs/contributing.md`](docs/contributing.md).
