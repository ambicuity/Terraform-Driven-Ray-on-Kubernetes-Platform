# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `main` | Yes |
| latest tagged release | Yes |
| older releases | No |

## Reporting a vulnerability

Do not open a public issue for security vulnerabilities.

Email the repository maintainers with:

- a clear description of the problem
- reproduction steps
- impact assessment
- any suggested remediation

## Response targets

| Milestone | Target |
|---|---|
| acknowledgment | 48 hours |
| initial assessment | 5 business days |
| remediation plan | 15 business days |

## Current controls

- short-lived GitHub workflow tokens for repository automation
- GitHub app integrations for CodeRabbit and Gemini Code Assist
- AWS OIDC for cloud-facing workflows
- KMS encryption, IMDSv2, IRSA, and OPA guardrails in infrastructure
- `CI`, `CodeQL`, and `Gitleaks` as the core repository checks

See [docs/security.md](docs/security.md) for the detailed architecture notes.
