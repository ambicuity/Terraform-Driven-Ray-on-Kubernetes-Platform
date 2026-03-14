# Autoscaling

The repository now treats autoscaling as two separate layers:

1. Platform scaling in Terraform (`terraform/`)
2. Ray workload scaling in the Helm chart and the complete example

## Platform Layer

The Terraform module defines the available capacity envelopes:

- CPU node group
- primary GPU node group
- optional On-Demand GPU fallback node group

Cluster Autoscaler is not installed by the root module. The IRSA role is exported so a downstream stack can deploy it safely.

## Workload Layer

The workload layer is managed by:

- `helm/ray/` for the `RayCluster`
- `terraform/examples/complete/helm.tf` for composing KubeRay, Cluster Autoscaler, and the Ray chart

The chart enables Ray in-tree autoscaling by default and defines separate CPU and GPU worker groups.

## Spot GPU Reliability

The previous repo story implied Spot-only GPU capacity was enough by itself. That is no longer the documented position.

Current guidance:

- Use `gpu_capacity_type = "SPOT"` for the primary GPU pool when you want the FinOps benefit
- Keep `enable_gpu_ondemand_fallback = true` unless you have consciously accepted Spot-only risk
- Keep fallback min and desired sizes at `0` if you want cost control while still preserving emergency capacity

Why:

- Ray can recover tasks and objects
- AWS can still reclaim an entire Spot pool at once
- without an On-Demand fallback node group, the autoscaler has nowhere reliable to place replacement GPU pods

## Local Validation

The local harness does not simulate AWS Spot reclamation. Instead, the repo validates the fallback design structurally:

- Terraform tests assert that Spot GPU mode creates an On-Demand fallback group by default
- OPA policy denies Spot GPU node groups without an On-Demand fallback
- `local_test.sh` focuses on the chart-backed CPU/HA path in minikube
