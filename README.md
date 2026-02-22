# Terraform Module: Ray on Kubernetes (EKS)

[![Terraform Validate](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/terraform-ci.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/terraform-ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-grade Terraform module for provisioning a robust, autoscaling Kubernetes (EKS) cluster optimized for Ray ML workloads. 

This module provides the necessary AWS infrastructure including VPC networking, EKS control plane, autoscaling CPU/GPU node groups, IAM Roles for Service Accounts (IRSA), and necessary security groups. It is designed to be highly configurable and ready to integrate with the [KubeRay Operator](https://docs.ray.io/en/latest/cluster/kubernetes/getting-started.html).

## Features

- **Decoupled Architecture**: Designed to be deployed into an existing VPC network (bring-your-own-network).
- **KMS Secret Encryption**: Kubernetes secrets are encrypted at rest using AWS KMS.
- **EKS Cluster**: Provisions a fully functional EKS control plane.
- **Node Groups**: Supports separate, autoscaling CPU and GPU node groups.
- **GPU Spot Instances & Taints**: GPU nodes default to **SPOT** capacity for extreme cost optimization. They are also automatically tainted to prevent non-GPU workloads from consuming expensive resources.
- **Autoscaler Ready**: Configures IAM permissions and IRSA for the Kubernetes Cluster Autoscaler so you can easily deploy the Helm chart.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                   │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                    VPC (10.0.0.0/16)                       │   │
│  │                                                            │   │
│  │  ┌─────────────────┐           ┌─────────────────┐        │   │
│  │  │ Public Subnets  │           │ Private Subnets │        │   │
│  │  │                 │           │                 │        │   │
│  │  │ • NAT Gateway   │           │ • EKS Nodes     │        │   │
│  │  │ • Load Balancer │           │ • Ray Pods      │        │   │
│  │  └────────┬────────┘           └────────┬────────┘        │   │
│  │           │                             │                 │   │
│  │           └─────────────┬───────────────┘                 │   │
│  └─────────────────────────┼─────────────────────────────────┘   │
│                            │                                     │
│  ┌─────────────────────────┼─────────────────────────────────┐   │
│  │         EKS Cluster      ↓                                 │   │
│  │                                                            │   │
│  │  ┌──────────────────────────────────────────────────┐     │   │
│  │  │            Control Plane                         │     │   │
│  │  │  • API Server  • Scheduler  • etcd              │     │   │
│  │  └──────────────────┬───────────────────────────────┘     │   │
│  │                     │                                     │   │
│  │  ┌──────────────────┼───────────────────────────────┐     │   │
│  │  │  Node Groups     ↓                               │     │   │
│  │  │                                                  │     │   │
│  │  │  ┌─────────────────┐    ┌─────────────────┐     │     │   │
│  │  │  │  CPU Workers    │    │  GPU (Spot)     │     │     │   │
│  │  │  │                 │    │                 │     │     │   │
│  │  │  │ • m5.xlarge     │    │ • g4dn.xlarge   │     │     │   │
│  │  │  │ • Autoscaling   │    │ • Autoscaling   │     │     │   │
│  │  │  └─────────────────┘    └─────────────────┘     │     │   │
│  │  │                                                  │     │   │
│  │  │  ┌────────────────────────────────────────┐     │     │   │
│  │  │  │         Ray Cluster (Pods)             │     │     │   │
│  │  │  │                                        │     │     │   │
│  │  │  │  ┌──────────┐  ┌────────────────────┐  │     │     │   │
│  │  │  │  │ Ray Head │  │   Ray Workers      │  │     │     │   │
│  │  │  │  └──────────┘  └────────────────────┘  │     │     │   │
│  │  │  └────────────────────────────────────────┘     │     │   │
│  │  └──────────────────────────────────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Usage

Here is a minimal example of how to use this module:

```hcl
module "ray_eks_cluster" {
  source = "github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform"

  cluster_name = "my-ray-cluster"
  region       = "us-east-1"
  
  # Network Configuration (Bring Your Own VPC)
  vpc_id     = "vpc-0abcd1234efgh5678"
  subnet_ids = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]

  cpu_node_min_size     = 2
  cpu_node_max_size     = 10
  cpu_node_desired_size = 2

  enable_gpu_nodes      = true
  gpu_node_min_size     = 0
  gpu_node_max_size     = 5
  gpu_node_desired_size = 0
}
```

For a complete runnable example, see the [examples/complete](examples/complete) directory.

## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.6.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 5.0 |
| <a name="requirement_kubernetes"></a> [kubernetes](#requirement\_kubernetes) | >= 2.0 |
| <a name="requirement_tls"></a> [tls](#requirement\_tls) | >= 4.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| `cluster_name` | Name of the EKS cluster | `string` | `"ray-ml-cluster"` | no |
| `region` | AWS region | `string` | `"us-east-1"` | no |
| `vpc_id` | ID of the existing VPC | `string` | n/a | yes |
| `subnet_ids` | List of subnet IDs | `list(string)` | n/a | yes |
| `kms_key_arn` | ARN of KMS key for encryption | `string` | `""` | no |
| `enable_gpu_nodes` | Whether to create a GPU node group | `bool` | `true` | no |
| `cpu_node_instance_types` | Instance types for CPU nodes | `list(string)` | `["m5.xlarge", "m5a.xlarge"]` | no |
| `cpu_node_min_size` | Minimum size of CPU node group | `number` | `2` | no |
| `cpu_node_max_size` | Maximum size of CPU node group | `number` | `10` | no |
| `gpu_node_instance_types` | Instance types for GPU nodes | `list(string)` | `["g4dn.xlarge"]` | no |
| `gpu_node_min_size` | Minimum size of GPU node group | `number` | `0` | no |
| `gpu_node_max_size` | Maximum size of GPU node group | `number` | `5` | no |

*(For a full list of inputs, see `variables.tf`)*

## Outputs

| Name | Description |
|------|-------------|
| `cluster_name` | EKS cluster name |
| `cluster_endpoint` | EKS cluster endpoint URL |
| `kubeconfig_command` | Command to configure kubectl |
| `cluster_autoscaler_iam_role_arn` | IAM Role ARN for Cluster Autoscaler |

*(For a full list of outputs, see `outputs.tf`)*

## Deploying Workloads (Helm/Operators)

This module handles the heavy lifting of the AWS infrastructure natively. Additionally, we provide an out-of-the-box native Helm integration (see `examples/complete/helm.tf`) that automatically deploys:

1. **Cluster Autoscaler**: Native scaling tied to your IAM IRSA role.
2. **KubeRay Operator**: The Ray ML control plane, ready immediately.

If you leverage the module via the complete example, you can literally `terraform apply` and have a production-ready Ray platform available moments later without running a single manual `helm install` command.

An example Ray configuration (`values.yaml`) for a bursty Ray workload is provided in the `helm/ray/` directory of this repository for reference.

## License

MIT License. See [LICENSE](LICENSE) for details.
