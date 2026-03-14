# Contributing Guide

Thank you for contributing to Terraform-Driven Ray on Kubernetes Platform.

## Before you start

- Use a focused branch and keep changes scoped to one concern when possible.
- If you are changing Terraform examples or docs, keep the Terraform module source pinned to a tag.
- If you are changing workflows, preserve path-scoped CI behavior.

## Local validation

Run the checks that match the files you changed.

### Infrastructure

```bash
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
terraform fmt -check -recursive terraform/
terraform -chdir=terraform test
opa test policies -v
```

### Workloads

```bash
python -m compileall workloads validation
helm lint helm/ray
helm template ray-ci helm/ray >/tmp/ray-rendered.yaml
kube-score score /tmp/ray-rendered.yaml --ignore-test container-security-context-privileged --output-format ci
```

### Automation

```bash
python -m compileall scripts tests
python -m pytest tests -q
```

If you changed GitHub Actions workflows, also run:

```bash
actionlint
```

## Pull requests

- Use a Conventional Commit title such as `fix: scope CI for Terraform-only changes`.
- Describe what changed, why it changed, and how you tested it.
- Use CodeRabbit or Gemini Code Assist only if you want optional advisory feedback.

## AI policy

The supported AI surfaces are:

- CodeRabbit
- Gemini Code Assist on GitHub

Repo-owned AI workflows and autonomous PR bots are intentionally disabled in favor of a small deterministic CI surface.
