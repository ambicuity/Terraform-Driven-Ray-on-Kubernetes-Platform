# tests/ — Agent Unit Tests

This directory contains unit tests for all four Autonomous AI Agent scripts.

## Conventions

| File | Tests |
|---|---|
| `test_gamma.py` | Agent Gamma — duplicate detection, marker validation, priority assignment |
| `test_delta.py` | Agent Delta — queue selection, import hallucination detection, preflight check |
| `test_beta.py` | Agent Beta — hallucinated import scanning, approval/rejection decision |
| `test_alpha.py` | Agent Alpha — SemVer bump logic, CHANGELOG synthesis, governance guard |
| `fixtures/github_api_fixtures.py` | Shared realistic mock payloads (real GitHub API shapes) |

## Running Tests

```bash
# From the repository root
python -m pytest tests/ -v

# Run a single file
python -m pytest tests/test_gamma.py -v

# Standard library only — no extra deps required
python -m unittest discover tests/
```

## Mock Data Standards

All test fixtures in `fixtures/github_api_fixtures.py` use **realistic** GitHub API response
shapes based on the [GitHub REST API documentation](https://docs.github.com/en/rest).
Payloads are not minimal stubs — they include the fields that the agent scripts actually read.

## Coverage Targets

Each test module targets at least 3 test cases:

1. **Happy path** — valid data, expected output
2. **Missing/invalid input** — missing fields, empty strings
3. **Edge case / error** — boundary conditions, API error simulation
