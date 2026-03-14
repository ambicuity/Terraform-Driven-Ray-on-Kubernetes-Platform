# Security Architecture

This document describes the current security model for infrastructure, workloads, and GitHub automation.

## Identity and access

### GitHub automation

- Repository workflows use the short-lived `GITHUB_TOKEN` with least-privilege permissions.
- CodeRabbit and Gemini Code Assist are installed GitHub apps. They are advisory review surfaces, not merge gates.

The repository does not rely on repo-owned AI workflows, custom Gemini CLI credentials, or long-lived GitHub application keys for normal workflow execution.

### AWS access

- AWS access in automation should use GitHub OIDC federation.
- [`drift-detection.yml`](../.github/workflows/drift-detection.yml) is the only remaining workflow that touches AWS directly.
- Static AWS access keys should not be used in repository workflows.

Example trust-policy scoping:

```json
{
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
    },
    "StringLike": {
      "token.actions.githubusercontent.com:sub": "repo:ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform:*"
    }
  }
}
```

## Infrastructure controls

- EKS secrets use KMS envelope encryption.
- Launch templates enforce IMDSv2.
- GPU nodes use taints and Spot interruption handling.
- IRSA is preferred for cluster-level AWS access.
- OPA policies enforce guardrails before deployment.

## CI and policy controls

| Control | Where it runs |
|---|---|
| Terraform formatting, validation, tests | `CI / infra-ci` |
| OPA policy tests | `CI / infra-ci` |
| Helm lint and render checks | `CI / app-ci` |
| `kube-score` | `CI / app-ci` |
| Python compile and tests | `CI / automation-ci` |
| Docs consistency checks | `CI / docs-meta` |
| CodeQL | `codeql.yml` |
| Gitleaks | `gitleaks.yml` |

## Separation of concerns

This repository intentionally keeps infrastructure and workloads in one repository. That is workable only if workflow scoping is strict. The security posture therefore depends on:

1. path-scoped CI to reduce unnecessary blast radius
2. pinned Terraform Git sources for downstream module consumers
3. least-privilege workflow permissions
4. keeping AI assistants advisory instead of merge-blocking

## Review checklist

When reviewing security-sensitive changes, prioritize these questions:

- Does this introduce or reintroduce static cloud credentials?
- Does this widen a workflow trigger or permission scope unnecessarily?
- Does this point Terraform at a moving GitHub branch instead of a pinned ref?
- Does this couple workload-only changes to infrastructure validation or deployment?
- Do the OPA policies still match the actual Terraform and Helm layout?
