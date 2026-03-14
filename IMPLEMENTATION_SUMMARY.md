# Implementation Summary

The repository now keeps a committed local evidence bundle under `tests/evidence/`.

## Canonical local proof

- `make evidence` is the top-level entrypoint for generating the local proof set.
- `tests/evidence/run_local_evidence.sh` saves stable output files for bootstrap, lint, tests, claim audit, and the chart-backed minikube run.
- `tests/evidence/SUMMARY.md` links every proof step to the saved transcript that was committed.

## Supported claims

The repository only retains claims that are backed by code or deterministic structure today:

- launch templates are attached to the managed node groups
- Spot GPU mode creates an On-Demand fallback path by default
- OIDC thumbprint drift is handled explicitly
- the Ray chart renders head probes, a `preStop` hook, and a CPU-worker PodDisruptionBudget
- the cluster identity safeguard is implemented and unit-tested
- deterministic CI, local test, and evidence entrypoints are defined in-repo

See `tests/evidence/claim-matrix.md` for the full claim-to-proof mapping.

## Scope discipline

- Extended AWS-only or GPU-only scripts stay in `validation/` and `workloads/`.
- Those scripts are not presented as locally proven unless their transcripts are also saved under `tests/evidence/`.
- Unsupported historical checklist items were removed so the summary reflects the current repository instead of an aspirational state.
