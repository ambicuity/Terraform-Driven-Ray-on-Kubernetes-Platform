# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch | ✅ Active |
| Tagged releases | ✅ Latest only |
| Older releases | ❌ Not supported |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### Reporting Process

1. **Email**: Send a detailed report to the repository maintainers via the contact information in their GitHub profiles.
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if any)

### Response Timeline

| Milestone | Target |
|-----------|--------|
| Acknowledgment | 48 hours |
| Initial assessment | 5 business days |
| Fix development | 15 business days |
| Disclosure | After fix is released |

### What Qualifies

- Terraform misconfigurations that expose resources publicly
- IAM policy over-permissions
- Secret exposure in logs, outputs, or state files
- Container escape vectors in node user-data scripts
- OPA policy bypasses
- CI/CD pipeline injection risks

### What Does Not Qualify

- Issues in upstream dependencies (AWS provider, EKS, Ray) — report those upstream
- Theoretical attacks without a practical exploitation path
- Issues requiring physical access to the AWS account
- Denial-of-service via resource exhaustion (covered by OPA policies)

## Security Controls

This project implements the following security measures. See [docs/security.md](docs/security.md) for full details.

- **No long-lived credentials** — GitHub App tokens (1-hour expiry) + AWS OIDC federation
- **Encryption at rest** — KMS envelope encryption for Kubernetes secrets, encrypted EBS volumes
- **IMDSv2 enforcement** — Blocks SSRF-based credential theft
- **OPA policy governance** — Enforces resource limits, encryption, and tagging
- **CI security scanning** — tfsec, Checkov, CodeQL, Gitleaks on every PR
- **Private endpoints** — EKS API server not publicly accessible by default
- **Pod security** — Non-root containers, restricted fsGroup
