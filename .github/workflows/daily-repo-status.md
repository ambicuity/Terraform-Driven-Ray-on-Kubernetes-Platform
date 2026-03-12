---
description: |
  This workflow creates daily repo status reports. It gathers recent repository
  activity (issues, PRs, discussions, releases, code changes) and generates
  engaging GitHub issues with productivity insights, community highlights,
  and project recommendations.

on:
  schedule: weekly on monday
  workflow_dispatch:

permissions:
  contents: read
  issues: read
  pull-requests: read

network: defaults

tools:
  github:
    # If in a public repo, setting `lockdown: false` allows
    # reading issues, pull requests and comments from 3rd-parties
    # If in a private repo this has no particular effect.
    lockdown: false

safe-outputs:
  mentions: false
  allowed-github-references: []
  create-issue:
    title-prefix: "[repo-status] "
    labels: [report, repo-status]
    close-older-issues: true
source: githubnext/agentics/workflows/daily-repo-status.md@346204513ecfa08b81566450d7d599556807389f
engine: copilot
---

# Weekly Repo Status

Create one concise weekly repository status issue for maintainers.

## What to include

- Recent repository activity across issues, PRs, releases, and workflows
- Notable risks, blockers, and stale areas
- Concrete next steps that help maintainers keep the repo healthy

## Style

- Be concise, factual, and operational
- Avoid hype and avoid long narrative sections
- Keep the output issue-only

## Repository-specific emphasis

- Call out if Terraform, Helm/workload, Python automation, docs, and policy changes are staying properly separated in review and CI.
- Mention docs drift or workflow sprawl if you see it.
