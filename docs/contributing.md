# Contributing Guide

Thank you for your interest in contributing to the Terraform-Driven-Ray-on-Kubernetes-Platform project.

## Development Setup

### Prerequisites

- Terraform >= 1.6.0
- Python >= 3.10
- Go (for OPA/Rego testing)
- Node.js / npm (for markdown link checking)
- Pre-commit (optional but recommended)

### Local Validation

```bash
# Terraform
terraform init
terraform validate
terraform fmt -check -recursive

# TFLint
tflint --init
tflint

# Python linting
pip install flake8 black
flake8 scripts/
black --check scripts/

# OPA policy tests
opa test policies/ -v

# Terraform tests (offline, uses mock providers)
terraform test
```

---

## Branch Naming Convention

| Type | Format | Example |
|------|--------|---------|
| Feature | `feat/<short-description>` | `feat/add-fargate-support` |
| Bug fix | `fix/<short-description>` | `fix/gpu-taint-missing` |
| Documentation | `docs/<short-description>` | `docs/add-architecture-guide` |
| CI/CD | `ci/<short-description>` | `ci/add-trivy-scanning` |
| Refactor | `refactor/<short-description>` | `refactor/extract-iam-module` |

---

## PR Conventions

### Title Format

PRs must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description>
```

**Valid types**: `feat`, `fix`, `docs`, `ci`, `refactor`, `test`, `chore`, `perf`

**Examples**:
- `feat: add Fargate profile for Ray head node`
- `fix: correct GPU taint key in node_pools.tf`
- `docs: add autoscaling tuning guide`

### PR Body

Include:
1. **What** — Brief description of the change
2. **Why** — Motivation or issue reference (`Closes #N`)
3. **Testing** — How you validated the change

### Size

- Keep PRs focused and scoped to a single concern
- Prefer smaller, reviewable PRs over large monolithic changes
- If a change spans multiple components, consider splitting into stacked PRs

---

## CI Gates

All of the following must pass before a PR can be merged:

| Gate | Workflow | What It Checks |
|------|----------|----------------|
| Terraform CI | `terraform-ci.yml` | `init`, `validate`, `fmt -check` |
| TFSec | `tfsec.yml` | Terraform security scanning |
| TFLint | `tflint.yml` | Terraform linting |
| Checkov | `checkov.yml` | IaC policy compliance |
| Python Lint | `python-lint.yml` | Python code quality |
| PR Lint | `pr-lint.yml` | Conventional commit title |
| Kube-score | `kube-score.yml` | Kubernetes manifest quality |
| Markdown Links | `markdown-links.yml` | No broken links in docs |

### AI Bots (Advisory, Non-Blocking)

These bots post comments but do not block merge:
- **AI Code Reviewer** — Gemini-powered review
- **AI Test Engineer** — Suggested test cases
- **Duplicate Detector** — Checks for duplicate issues

---

## Code Style

### Terraform

- Follow [HashiCorp's Terraform style guide](https://developer.hashicorp.com/terraform/language/syntax/style)
- Run `terraform fmt -recursive` before committing
- Use descriptive variable names with `description` fields
- Include `validation` blocks for input constraints
- Add `# tfsec:ignore:<rule>` comments only with justification

### Python

- Follow PEP 8
- Use type hints for function signatures
- Include docstrings for public functions
- Use `black` for formatting, `flake8` for linting
- Zero external dependencies — use `urllib.request` from stdlib

### OPA/Rego

- Use `import rego.v1` for OPA 1.0 syntax
- Use `contains` keyword for set rules
- Include inline test cases (`test_*` rules)
- Separate `deny` (blocking) from `warn` (advisory)

---

## Testing Expectations

| Component | Test Type | Tool |
|-----------|----------|------|
| Terraform | Plan validation | `terraform test` with `mock_provider` |
| OPA policies | Unit tests | Inline `test_*` rules, `opa test` |
| Python scripts | Syntax + lint | `flake8`, `black --check` |
| Helm charts | Template validation | `helm template` + `kube-score` |
| Kubernetes manifests | Manifest scoring | `kube-score` |
| Markdown | Link validation | `markdown-link-check` |

---

## Issue Guidelines

When filing an issue, include:
1. **Type**: Bug, Enhancement, Documentation, or Question
2. **Description**: Clear, concise problem statement
3. **Reproduction steps** (for bugs): What you ran, what happened, what you expected
4. **Environment**: Terraform version, AWS region, EKS version

The AI Issue Solver bot will automatically post a structured implementation plan on new issues.

---

## Release Process

1. PRs merged to `main` are automatically picked up by the Release Drafter
2. The release drafter generates changelog entries from PR titles
3. Maintainers review and publish the draft release
4. Tags follow [Semantic Versioning](https://semver.org/) (`vX.Y.Z`)
