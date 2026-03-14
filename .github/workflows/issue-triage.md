---
description: |
  Intelligent issue triage assistant that processes new and reopened issues.
  Analyzes issue content, selects appropriate labels, detects spam, gathers context
  from similar issues, and provides analysis notes including debugging strategies,
  reproduction steps, and resource links. Helps maintainers quickly understand and
  prioritize incoming issues.

on:
  issues:
    types: [opened, reopened]
  reaction: eyes

permissions: read-all

network: defaults

safe-outputs:
  add-labels:
    allowed:
      - bug
      - documentation
      - duplicate
      - enhancement
      - question
      - security
      - ci
      - infrastructure
      - ray
      - terraform
      - github_actions
      - P0-critical
      - P1-high
      - P2-medium
      - P3-low
      - type/bug
      - type/feature
      - type/refactor
      - type/docs
      - type/security
      - type/performance
      - type/question
      - type/design
      - area/terraform
      - area/kubernetes
      - area/ray
      - area/ci
      - area/opa
      - area/python
      - area/networking
      - area/iam
      - status/needs-info
    max: 5
  add-comment:
    max: 1

tools:
  github:
    toolsets: [issues]
    # If in a public repo, setting `lockdown: false` allows
    # reading issues, pull requests and comments from 3rd-parties
    # If in a private repo this has no particular effect.
    lockdown: false    

timeout-minutes: 10
source: githubnext/agentics/workflows/issue-triage.md@346204513ecfa08b81566450d7d599556807389f
engine: copilot
---

# Issue Triage

Triage issue #${{ github.event.issue.number }} for this repository.

## Repository Rules

- This repo contains Terraform, Helm workloads, Python automation, OPA policies, and docs in one place.
- Triage should help maintainers classify the issue. Do not create queue files, hidden state, or follow-up issues.
- Only use the allowed labels above.
- If the issue clearly needs reporter follow-up, use `status/needs-info`.
- Only use `duplicate` when the matching issue is still open.

## What good triage looks like here

1. Identify one `type/*` label when clear.
2. Identify one or two `area/*` labels when clear.
3. Add a priority label only when urgency is obvious from user impact.
4. Add one concise maintainer-facing comment that starts with `🎯 Agentic Issue Triage`.

## Comment format

- One short summary paragraph.
- Optional collapsed sections for `Reproduction Notes`, `Debugging Ideas`, and `Relevant Files or Docs`.
- Keep it concise and practical.
