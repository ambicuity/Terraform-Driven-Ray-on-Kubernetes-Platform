# Supported Claim Matrix

This matrix defines the claims the repository currently supports and how each one is proven locally.

| Claim | Backing implementation | Local proof path | Saved evidence |
| --- | --- | --- | --- |
| Launch templates are attached to the managed node groups. | `terraform/node_pools.tf`, `terraform/module.tftest.hcl` | `make test`, `python3 tests/evidence/check_supported_claims.py` | `20-make-test.txt`, `30-claims-audit.txt` |
| Spot GPU mode creates an On-Demand fallback path by default. | `terraform/node_pools.tf`, `terraform/module.tftest.hcl`, `policies/terraform_test.rego` | `make test`, `python3 tests/evidence/check_supported_claims.py` | `20-make-test.txt`, `30-claims-audit.txt` |
| OIDC thumbprint drift is handled with separate managed and unmanaged resources. | `terraform/main.tf` | `python3 tests/evidence/check_supported_claims.py` | `30-claims-audit.txt` |
| The Ray chart renders explicit head probes and a `preStop` hook. | `helm/ray/values.yaml`, `validation/local-chart-values.yaml`, `helm/ray/templates/raycluster.yaml` | `make lint`, `python3 tests/evidence/check_supported_claims.py`, `./local_test.sh` | `10-make-lint.txt`, `30-claims-audit.txt`, `40-local-test.txt` |
| The Ray chart renders a PodDisruptionBudget for CPU workers. | `helm/ray/templates/pdb.yaml` | `make lint`, `python3 tests/evidence/check_supported_claims.py` | `10-make-lint.txt`, `30-claims-audit.txt` |
| The cluster identity safeguard fingerprints the live cluster and is unit-tested. | `scripts/validate_cluster_identity.py`, `tests/test_validate_cluster_identity.py` | `make test`, `python3 tests/evidence/check_supported_claims.py` | `20-make-test.txt`, `30-claims-audit.txt` |
| Deterministic CI and local entrypoints are defined in-repo. | `Makefile`, `.github/workflows/ci.yml`, `local_test.sh` | `make lint`, `make test`, `make evidence`, `python3 tests/evidence/check_supported_claims.py` | `10-make-lint.txt`, `20-make-test.txt`, `30-claims-audit.txt`, `SUMMARY.md` |

## Extended Manual Validation

The following scripts remain useful, but they are environment-specific and are not counted as locally proven unless their outputs are also saved under this folder:

- `validation/test_scale_event.sh`
- `validation/test_gpu_density.sh`
- `validation/test_memory_spill.py`
- `workloads/ha_resilience_test.py`
- `workloads/chaos_test.py`
- `workloads/bursty_training.py`
