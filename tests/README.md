# Test Suite

This repository keeps only deterministic tests for the remaining operational scripts.

## Current coverage

- `test_validate_cluster_identity.py` validates kubeconfig discovery and cluster identity safeguards.
- `test_drift_detector.py` validates drift report parsing without reaching external services.

## Run locally

```bash
python -m pytest tests -q
```
