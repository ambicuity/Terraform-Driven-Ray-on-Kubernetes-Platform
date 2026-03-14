# Terraform-Driven Ray on Kubernetes Platform

[![CI](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/codeql.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/codeql.yml)
[![Gitleaks](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/gitleaks.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/gitleaks.yml)

This repository provides a production-oriented AWS EKS platform for running Ray workloads, with a clear separation between infrastructure and workload deployment:

- `terraform/` provisions the core EKS platform and worker node groups.
- `helm/ray/` renders a deployable `RayCluster` chart for KubeRay.
- `terraform/examples/complete/` shows the addon and workload layer: Cluster Autoscaler, KubeRay, the Ray chart, and optional Velero.
- `policies/` keeps a small Terraform-focused OPA ruleset.
- `validation/` and `local_test.sh` exercise the real chart-backed local path.

## What Changed

- The root Terraform module is now infra-only. It no longer creates Helm releases or Velero resources.
- GPU workloads are safe-by-default for Spot-heavy clusters: when the primary GPU pool uses `SPOT`, the module also creates a small On-Demand fallback pool unless you explicitly disable it.
- The launch templates described in the docs are now actually attached to the node groups.
- The Helm chart is a real chart with renderable templates, not just a values file.
- The repo keeps only lightweight advisory AI surfaces. Merge gates remain deterministic.

## Quick Start

Use the root module only for platform infrastructure:

```hcl
module "ray_eks_cluster" {
  source = "git::https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform.git//terraform?ref=v1.0.0"

  cluster_name = "production-ray-cluster"
  region       = "us-east-1"

  vpc_id     = "vpc-0abcd1234efgh5678"
  subnet_ids = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]

  cpu_node_min_size     = 2
  cpu_node_max_size     = 10
  cpu_node_desired_size = 3

  enable_gpu_nodes                   = true
  gpu_capacity_type                  = "SPOT"
  enable_gpu_ondemand_fallback       = true
  gpu_ondemand_fallback_max_size     = 1
  gpu_ondemand_fallback_desired_size = 0
}
```

Use `terraform/examples/complete/` when you also want the addon and workload layer.

## Local Validation

Terraform `>= 1.6.0` is required for the module test suite. The repository also includes a bundled binary at `.tmp-tools/bin/terraform-1.9.8` for local validation on machines with older installs.

Recommended checks:

```bash
make lint
make test
./local_test.sh
```

`local_test.sh` installs the real `helm/ray` chart on top of KubeRay in minikube instead of validating an inline throwaway manifest.

Optional review surfaces are CodeRabbit, Gemini Code Assist on GitHub, and official GitHub Agentic Workflows. They are advisory only. Merge gates remain deterministic through `CI`, `CodeQL`, and `Gitleaks`.

## Runtime Notes

- Spot GPU capacity is cost-efficient, but it is not treated as inherently reliable anymore. The default posture is Spot primary plus an On-Demand fallback node group.
- The core module still provisions EKS managed addons such as `vpc-cni`, `kube-proxy`, and `coredns`; it does not deploy Ray, KubeRay, Cluster Autoscaler, or Velero.
- Velero is available only in the example and addon layer.

## Documentation

- [Architecture](docs/architecture.md)
- [Terraform Module Reference](docs/terraform-module.md)
- [Autoscaling](docs/autoscaling.md)
- [Operations Guide](docs/operations-guide.md)
- [Security](docs/security.md)
- [CI/CD Pipelines](docs/ci-cd-pipelines.md)
- [Contributing](docs/contributing.md)
- [Terraform Module README](terraform/README.md)
- [Validation Runbook](validation/README.md)
