# Test Suite

The `tests/` package keeps the deterministic Python tests, while `tests/evidence/` stores the committed local proof bundle and saved command output.

## Current deterministic coverage

- `test_validate_cluster_identity.py` validates kubeconfig discovery and cluster identity safeguards.
- `test_drift_detector.py` validates drift report parsing without reaching external services.

## Evidence hub

- `tests/evidence/claim-matrix.md` maps each supported repository claim to its backing code and saved proof files.
- `tests/evidence/SUMMARY.md` is the generated index of the latest committed local run.
- `tests/evidence/30-claims-audit.txt` stores the structural supported-claim audit output.

## Run locally

For the full committed proof set:

```bash
make evidence
```

For just the Python test subset:

```bash
python -m pytest tests -q
```
