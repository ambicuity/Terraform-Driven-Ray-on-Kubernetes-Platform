# GitHub Automation

This repository uses three AI-assisted review surfaces and a small set of deterministic GitHub Actions.

## Supported AI surfaces

| Surface | Purpose | Trigger |
|---|---|---|
| CodeRabbit | PR review and planning assistance | `@coderabbitai review`, `@coderabbitai full review`, `@coderabbitai plan` |
| Gemini Code Assist on GitHub | Native PR summary and review | `/gemini summary`, `/gemini review` |
| GitHub Agentic Workflows (`gh-aw`) | Repo-level planning, triage, CI investigation, and hygiene reports | event-driven workflows in `.github/workflows/*.md` |

Custom Gemini CLI subagents, queue files, and repo-hosted autonomous PR bots are intentionally removed.

## Official GitHub Agentic Workflows

| Workflow source | Purpose | Output |
|---|---|---|
| `daily-repo-status.md` | Weekly repository status reporting | GitHub issue |
| `issue-triage.md` | New and reopened issue classification | labels + one triage comment |
| `plan.md` | `/plan` breakdown into small tasks | up to 5 linked `[task]` issues |
| `ci-doctor.md` | Failed `CI` workflow investigation | comment or investigation issue |
| `contribution-guidelines-checker.md` | PR process compliance review | optional comment + `contribution-ready` |
| `repository-quality-improver.md` | Weekly repo hygiene analysis | one maintenance issue |

The Markdown file is the source of truth. The corresponding `.lock.yml` file is generated with `gh aw compile`.

## Slash commands and bot commands

### Native AI commands

| Command | Owner |
|---|---|
| `/plan` | GitHub Agentic Workflows |
| `/gemini review` | Gemini Code Assist on GitHub |
| `/gemini summary` | Gemini Code Assist on GitHub |
| `@coderabbitai plan` | CodeRabbit |

### Repo bot commands

| Command | Purpose |
|---|---|
| `/assign [@user]` | Assign the issue or PR |
| `/unassign [@user]` | Remove an assignee |
| `/working` | Mark work as active |
| `/not-working` | Unassign yourself |
| `/blocked [reason]` | Mark the item as blocked |
| `/eta <timeframe>` | Post an ETA and mark work in progress |
| `/priority P0|P1|P2|P3` | Set a priority label |
| `/status in-progress|blocked|review|approved|needs-info` | Set a status label |
| `/duplicate #N` | Mark as duplicate and close |
| `/help` | Show the command help text |

The repo command workflow explicitly ignores `/plan`, `/gemini ...`, and the removed legacy commands so the installed apps remain the source of truth.

## Deterministic workflows that remain

| Workflow | Purpose |
|---|---|
| `ci.yml` | Path-scoped required CI gate |
| `codeql.yml` | CodeQL analysis |
| `gitleaks.yml` | Secret scanning |
| `drift-detection.yml` | Scheduled Terraform drift detection using AWS OIDC |
| `assignment-followup.yml` | Nudge assigned issues that have no linked open PR |
| `contributor-greeting.yml` | Welcome first-time issue and PR authors |
| `stale.yml` | Stale issue and PR management |
| `release-drafter.yml` | Draft release notes on `main` |

## Required repository setup

1. Install the GitHub apps:
   - CodeRabbit
   - Gemini Code Assist on GitHub
2. Add `COPILOT_GITHUB_TOKEN` for official `gh-aw` workflows.
3. Keep branch protection focused on deterministic checks such as `CI`, `CodeQL`, and `Gitleaks`.
4. Push the `v1.0.0` git tag before publishing docs that reference the pinned Terraform module source.

## What was removed

- `.github/actions/setup-gemini-cli`
- `.gemini/agents/*` and `.gemini/settings.json`
- custom AI workflows such as `gamma-triage.yml`, `delta-executor.yml`, `beta-reviewer.yml`, and `alpha-governor.yml`
- repo-hosted AI queue and memory artifacts such as `.ai_metadata/` and `.memory/`
