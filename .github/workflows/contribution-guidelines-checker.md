---
description: |
  Reviews incoming pull requests to verify they comply with the repository's
  contribution guidelines. Checks CONTRIBUTING.md and similar docs, then either
  labels the PR as ready or provides constructive feedback on what needs to be
  improved to meet the guidelines.

on:
  pull_request:
    types: [opened, synchronize]
  reaction: eyes

permissions: read-all

network: defaults

safe-outputs:
  add-labels:
    allowed: [contribution-ready]
    max: 1
  add-comment:
    max: 1

tools:
  github:
    toolsets: [default]
    # If in a public repo, setting `lockdown: false` allows
    # reading issues, pull requests and comments from 3rd-parties
    # If in a private repo this has no particular effect.
    #
    # This is important for this workflow to be able to read contribution guidelines
    lockdown: false

timeout-minutes: 10
source: githubnext/agentics/workflows/contribution-guidelines-checker.md@346204513ecfa08b81566450d7d599556807389f
engine: copilot
---

# Contribution Guidelines Checker

Review PR #${{ github.event.pull_request.number }} for contribution-process compliance only.

## Step 1: Find Contribution Guidelines

Search for contribution guidelines in the repository. Check these locations in order:

1. `CONTRIBUTING.md` in the root directory
2. `.github/CONTRIBUTING.md`
3. `docs/CONTRIBUTING.md` or `docs/contributing.md`
4. Contribution sections in `README.md`
5. Other repo-specific docs like `DEVELOPMENT.md`, `HACKING.md`

Use the GitHub tools to read these files. If no contribution guidelines exist, use general best practices.

## Step 2: Retrieve PR Details

Use the `get_pull_request` tool to fetch the full PR details including:
- Title and description
- Changed files list
- Commit messages

The PR content is: "${{ steps.sanitized.outputs.text }}"

## Step 3: Evaluate Compliance

Check the PR against the contribution guidelines for:

- **PR Title**: Does it follow the required format? Is it clear and descriptive?
- **PR Description**: Is it complete? Does it explain the what and why?
- **Commit Messages**: Do they follow the required format (if specified)?
- **Required Sections**: Are all required sections present (e.g., test plan, changelog)?
- **Documentation**: Are docs updated if required by guidelines?
- **Other Requirements**: Any repo-specific requirements mentioned in the guidelines

## Step 4: Take Action

**If the PR meets all contribution guidelines:**
- Add the `contribution-ready` label to the PR
- Optionally add one brief comment acknowledging compliance

**If the PR needs improvements:**
- Add a helpful comment that includes:
  - Specific guidelines that are not being met
  - Clear, actionable steps to bring the PR into compliance
  - Links to relevant sections of the contribution guidelines
- Do NOT add the `contribution-ready` label

## Important Guidelines

- Focus only on title, description, testing notes, and documentation expectations.
- Do not block on code quality or implementation details; those belong to deterministic CI and human review.
- Be concise.
