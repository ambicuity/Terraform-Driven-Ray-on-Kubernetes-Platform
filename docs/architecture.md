# Infrastructure Architecture

The repository now has a deliberate boundary:

- `terraform/` provisions platform infrastructure only.
- `helm/ray/` defines the Ray workload.
- `terraform/examples/complete/` is the place where the platform and workload layers are composed together.

## Core Platform

The root module provisions:

- an EKS cluster with KMS secret encryption
- CPU worker nodes
- GPU worker nodes
- an optional On-Demand GPU fallback node group when the primary GPU pool uses `SPOT`
- IAM for nodes and Cluster Autoscaler IRSA
- EKS managed addons (`vpc-cni`, `kube-proxy`, `coredns`)
- CloudWatch control-plane logging
- OIDC for IRSA

It does not provision:

- KubeRay
- Ray workloads
- Cluster Autoscaler Helm releases
- Velero

## Node Group Design

### CPU workers

- Default capacity: `ON_DEMAND`
- Instance families: `m6g.*`
- Launch template attached for IMDSv2, encrypted gp3 root volumes, and bootstrap userdata

### GPU workers

- Primary group respects `gpu_capacity_type`
- If the primary group uses `SPOT`, the module creates a second On-Demand fallback group by default
- Both GPU groups share the same launch template and taint pattern so the scheduler behavior stays consistent

This repo no longer treats Spot-only GPU capacity as a reliable default for stateful or recovery-sensitive GPU workloads.

## Network Model

- Worker nodes are expected to run in private subnets supplied by the caller
- Security groups allow node-to-node traffic within the worker security group
- Worker egress is open to `0.0.0.0/0` and `::/0`, with the expectation that private-subnet egress is mediated by NAT, egress controls, or upstream network policy

The earlier RFC1918-only egress assumption was too restrictive for a bring-your-own-VPC EKS design because nodes still need to reach AWS APIs and image registries.

## Addon / Workload Layer

The complete example installs:

- Cluster Autoscaler
- KubeRay operator
- the local `helm/ray` chart
- optional Velero

That split is intentional. It keeps the root Terraform module focused on reusable platform concerns while letting ML/workload deployment live in an example or a downstream stack.
