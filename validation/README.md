# Validation Runbook

This directory contains validation helpers for the platform and workload layers.

## Local

Run the committed local evidence bundle:

```bash
make evidence
```

This writes the saved transcripts to `tests/evidence/` and includes the chart-backed minikube harness as the required local cluster proof.

If you want to run only the chart-backed harness itself:

```bash
./local_test.sh
```

The harness:

- installs KubeRay
- installs the real `helm/ray` chart with `validation/local-chart-values.yaml`
- waits for the resulting Ray pods
- runs smoke validations against the live local cluster

## Structural Safety Checks

The Spot GPU fallback design is validated offline, not through a fake local Spot reclamation:

- Terraform tests assert Spot primary + On-Demand fallback by default
- OPA policy rejects Spot GPU plans without a fallback node group

## Live Cluster Scripts

- `test_scale_event.sh` checks cluster-autoscaler/CoreDNS behavior on a live cluster
- `test_gpu_density.sh` checks GPU node pod density on a live cluster
- `test_memory_spill.py` checks Ray object spilling behavior

These scripts are for real Kubernetes environments. They are not required for the local minikube smoke path.

When you do run them, save their output under `tests/evidence/` before presenting them as proof.
