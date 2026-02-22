# AI-Powered Automation Suite

This project includes four Gemini-powered AI bots that run as GitHub Actions to automate code review, issue analysis, test generation, and duplicate detection.

## Bot Overview

| Bot | Script | Trigger | Workflow |
|-----|--------|---------|----------|
| **AI Code Reviewer** | `scripts/ai_review.py` | PR opened/updated | `.github/workflows/ai-review.yml` |
| **AI Issue Solver** | `scripts/ai_issue_solver.py` | Issue opened, `/plan` or `/replan` command | `.github/workflows/ai-issue-solver.yml` |
| **AI Test Engineer** | `scripts/ai_test_engineer.py` | PR opened/updated | `.github/workflows/ai-test-engineer.yml` |
| **AI Duplicate Detector** | `scripts/ai_duplicate_detector.py` | Issue opened | `.github/workflows/ai-duplicate-detector.yml` |

All bots use the **Gemini `gemini-3-flash-preview`** model via the Generative Language REST API.

## Required Secrets

| Secret | Description |
|--------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions |

No additional secrets are required. All bots use the default `GITHUB_TOKEN` for posting comments.

---

## AI Code Reviewer

**Purpose**: Performs a CodeRabbit-style automated code review on every pull request.

**How it works**:
1. Fetches the PR diff via `GET /repos/{owner}/{repo}/pulls/{number}` with `Accept: application/vnd.github.v3.diff`
2. Fetches PR metadata (title, author, changed files, additions/deletions)
3. Sends the diff + metadata to Gemini with a system prompt covering Terraform, Kubernetes, AWS, OPA, Python, and CI/CD
4. Posts the review as a PR comment with the header `🤖 Gemini AI Review`

**Review output structure**:
- **Summary** — 2-3 sentence overview
- **Security Review** — Exposed secrets, IAM issues, missing encryption
- **Best Practices** — Anti-patterns in Terraform/K8s/Python
- **Suggestions** — Actionable improvements with code snippets
- **Risk Assessment** — Low / Medium / High rating

**Configuration**: Diff truncated at 60,000 characters. Gemini called with `temperature: 0.3` and `maxOutputTokens: 4096`.

**Retry logic**: Retries on HTTP 429/500/503 with backoff delays of 10s, 30s, 60s.

---

## AI Issue Solver

**Purpose**: Analyzes newly created issues and generates a structured implementation plan.

**How it works**:
1. Fetches the issue title, body, labels, and author
2. Fetches the repository file tree (filtered to `.tf`, `.py`, `.rego`, `.yml`, `.md`, `.json`, `.hcl`)
3. Sends the issue context + file tree to Gemini
4. Posts a structured solution plan as an issue comment

**Output structure**:
- **🔍 Root Cause Analysis** — What is causing the issue
- **📋 Implementation Plan** — Numbered steps with file paths
- **📁 Files to Modify** — Specific file list
- **⚠️ Risk Assessment** — Complexity, breaking changes, effort
- **🧪 Testing Strategy** — Verification approach

**Slash commands**: The bot can also be triggered via `/plan` or `/replan` comments (handled by `bot-commands.yml` workflow).

---

## AI Test Engineer

**Purpose**: Generates concrete, runnable test code for PR changes.

**How it works**:
1. Fetches the PR diff and metadata
2. Sends to Gemini with a test-generation system prompt
3. Posts test suggestions as a PR comment

**Test generation rules**:
- Python changes → `pytest` test functions with fixtures
- Terraform changes → `tftest.hcl` mock-based test blocks
- OPA/Rego changes → `conftest` test data and expected results
- Helm changes → `helm template` + kube-score validation steps

Generates **real test code**, not pseudocode. Includes edge cases.

---

## AI Duplicate Detector

**Purpose**: Scans for duplicate issues when a new issue is created.

**How it works**:
1. Fetches the new issue details
2. Fetches all open issues (up to 500, paginated)
3. Filters out pull requests (GitHub API returns PRs as issues)
4. Sends the new issue + existing issues to Gemini for comparison
5. Posts results as an issue comment

**Duplicate detection rules**:
- Only flags **genuinely identical** problems or feature requests
- "Related" issues about the same component but different aspects are **not** duplicates
- Conservative — false positives are worse than false negatives

**Output**: A table of potential duplicates with similarity rating and recommendation, or a `✅ No duplicate issues detected` message.

---

## Common Architecture

All four scripts share the same architectural pattern:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  GitHub API  │────>│ Gemini API   │────>│ GitHub API   │
│  (fetch)     │     │ (analyze)    │     │ (post)       │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Shared traits**:
- Zero external dependencies — uses only `urllib.request` from Python stdlib
- Structured error handling with `sys.exit(1)` on fatal errors
- Environment variable validation before execution
- Retry logic with exponential backoff for Gemini API rate limits
- Diff/body truncation to stay within token limits
