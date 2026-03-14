# Agentic Workflow Instructions

Use these repository rules whenever an official GitHub Agentic Workflow is active.

## Repo Shape

- This repository intentionally keeps Terraform, Helm workloads, OPA policies, Python automation, and documentation in one repo.
- CI is path-scoped on purpose. Do not recommend workflow changes that would make a docs-only or automation-only change trigger the full infra validation stack.
- Keep AI outputs advisory. Deterministic GitHub Actions are the merge gate.

## Supported AI Surfaces

- Official GitHub Agentic Workflows (`gh-aw`) using the `copilot` engine
- CodeRabbit for PR review and planning assistance
- Gemini Code Assist on GitHub for `/gemini review` and `/gemini summary`

Do not suggest reintroducing Gemini CLI subagents, queue files, hidden memory stores, or repo-hosted autonomous PR-writing bots.

## Label Taxonomy

- Priority labels: `P0-critical`, `P1-high`, `P2-medium`, `P3-low`
- Status labels: `status/in-progress`, `status/blocked`, `status/needs-review`, `status/approved`, `status/needs-info`
- Area labels: `area/terraform`, `area/kubernetes`, `area/ray`, `area/ci`, `area/opa`, `area/python`, `area/networking`, `area/iam`
- Type labels: `type/bug`, `type/feature`, `type/refactor`, `type/docs`, `type/security`, `type/performance`, `type/question`, `type/design`

Avoid using deprecated labels such as `status:triaged`, `priority:high`, `priority:medium`, `priority:low`, `ai-generated`, `ai-review`, and `skip-ai`.

## Planning Guidance

- The official `/plan` workflow should create at most 5 linked `[task]` issues.
- Keep tasks small enough for a single PR.
- Preserve repo boundaries in the task breakdown:
  - infra work: `terraform/`, `policies/`
  - workload work: `helm/`, `workloads/`, `validation/`
  - automation work: `scripts/`, `tests/`, `.github/workflows/`
  - docs work: `README.md`, `docs/`, contribution and security docs

## Review Guidance

- Flag any Terraform module source that points at GitHub without a pinned `?ref=`.
- Treat static AWS credentials in workflows as a security issue.
- Prefer least-privilege permissions in workflows.
- Focus on operational blast radius, not style nits.
