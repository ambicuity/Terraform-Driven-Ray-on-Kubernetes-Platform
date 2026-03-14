# Implemented Reliability Mitigations

This document lists only the mitigations that are implemented in the repository today and are compatible with the local evidence workflow.

## 1. Head readiness and graceful shutdown

**Problem:** Head-pod replacement can surface traffic before Ray is ready or cut off in-flight work during termination.

**Implemented mitigation:**

- `helm/ray/values.yaml` defines explicit head readiness and liveness probes.
- `helm/ray/values.yaml` also defines a `preStop` hook that runs `ray stop --grace-period=30`.
- `validation/local-chart-values.yaml` keeps the local evidence path on the same chart-backed mechanism.

**Local proof:** `python3 tests/evidence/check_supported_claims.py` and `./local_test.sh`

## 2. Worker disruption safety

**Problem:** Voluntary disruption can evict Ray workers too aggressively if there is no workload-aware disruption budget.

**Implemented mitigation:**

- `helm/ray/templates/pdb.yaml` renders a PodDisruptionBudget for CPU workers with `minAvailable: 1`.

**Local proof:** `python3 tests/evidence/check_supported_claims.py`

## 3. OIDC thumbprint drift control

**Problem:** AWS-managed thumbprints can cause noisy or perpetual Terraform drift on the OIDC provider resource.

**Implemented mitigation:**

- `terraform/main.tf` splits the OIDC provider into managed and unmanaged resources.
- The unmanaged path uses `ignore_changes = [thumbprint_list]` so AWS-populated thumbprints do not create churn by default.

**Local proof:** `make test` and `python3 tests/evidence/check_supported_claims.py`

## 4. Stale kubeconfig detection

**Problem:** Recreated clusters with reused names can leave stale kubeconfig state behind and cause confusing client failures.

**Implemented mitigation:**

- `scripts/validate_cluster_identity.py` fingerprints the live cluster from the `kube-system` namespace UID.
- `tests/test_validate_cluster_identity.py` covers kubeconfig lookup and failure-mode exit behavior.

**Local proof:** `make test` and `python3 tests/evidence/check_supported_claims.py`

## Evidence boundary

This repository does not currently claim a lightweight init-container OOM mitigation or an ASG lifecycle-hook mitigation because those implementations are not present in the current codebase.
