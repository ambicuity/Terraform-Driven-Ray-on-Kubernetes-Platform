# Security

## Identity and Access

- GitHub workflows use the short-lived `GITHUB_TOKEN`
- AWS access for automation is expected to use GitHub OIDC federation
- The root Terraform module configures EKS OIDC so downstream addons can use IRSA

## Platform Controls

- Kubernetes secrets are encrypted with KMS
- Launch templates require IMDSv2
- Root volumes are encrypted gp3
- Worker node groups are private-subnet oriented and rely on upstream NAT/egress controls
- OPA policies enforce a small set of Terraform-aligned guardrails

## Spot GPU Policy

This repo no longer treats Spot-only GPU capacity as a security or reliability control by itself.

The current default is:

- primary GPU pool may use `SPOT`
- an On-Demand fallback GPU pool is created automatically unless explicitly disabled

That is a reliability posture, but it also reduces operational pressure to make unsafe emergency changes after Spot exhaustion.

## Repo Automation

The repo keeps only advisory AI review surfaces:

- CodeRabbit
- Gemini Code Assist on GitHub
- repository-level Copilot instructions

These are not merge gates. Required merge gates are deterministic CI, CodeQL, and Gitleaks.
