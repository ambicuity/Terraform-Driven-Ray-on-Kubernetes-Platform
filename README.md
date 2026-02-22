# Terraform Module: Ray on Kubernetes (EKS)

[![Terraform Validate](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/terraform-ci.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/terraform-ci.yml)
[![TFSec](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/tfsec.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/tfsec.yml)
[![TFLint](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/tflint.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/tflint.yml)
[![Checkov](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/checkov.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/checkov.yml)
[![Kube-score](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/kube-score.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/kube-score.yml)
[![CodeQL](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/codeql.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/codeql.yml)
[![Python Lint](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/python-lint.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/python-lint.yml)
[![AI Review](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/ai-review.yml/badge.svg)](https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/actions/workflows/ai-review.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-grade Terraform module for provisioning a robust, autoscaling Kubernetes (EKS) cluster optimized for Ray ML workloads. 

This module provides the necessary AWS infrastructure including VPC networking, EKS control plane, autoscaling CPU/GPU node groups, IAM Roles for Service Accounts (IRSA), and necessary security groups. It is designed to be highly configurable and ready to integrate with the [KubeRay Operator](https://docs.ray.io/en/latest/cluster/kubernetes/getting-started.html).

## Features

- **Decoupled Architecture**: Designed to be deployed into an existing VPC network (bring-your-own-network).
- **KMS Secret Encryption**: Kubernetes secrets are encrypted at rest using AWS KMS.
- **EKS Cluster**: Provisions a fully functional EKS control plane.
- **Node Groups**: Supports separate, autoscaling CPU and GPU node groups.
- **GPU Spot Instances & Fault Tolerance**: GPU nodes default to **SPOT** capacity for extreme cost optimization. Ray's built-in fault tolerance (via the object store and worker respawning) makes it inherently resilient to AWS Spot interruptions. Nodes are also automatically tainted to prevent non-GPU workloads from consuming expensive resources.
- **Autoscaler Ready**: Configures IAM permissions and IRSA for the Kubernetes Cluster Autoscaler so you can easily deploy the Helm chart.

## Architecture

![Architecture Diagram](diagrams/architecture.png)

*(A conceptual high-level flow is provided below for immediate reference).*

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

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.6.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 5.0 |
| <a name="requirement_kubernetes"></a> [kubernetes](#requirement\_kubernetes) | >= 2.0 |
| <a name="requirement_tls"></a> [tls](#requirement\_tls) | >= 4.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 5.0 |
| <a name="provider_tls"></a> [tls](#provider\_tls) | >= 4.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_log_group.cluster](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_eks_addon.addons](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eks_addon) | resource |
| [aws_eks_cluster.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eks_cluster) | resource |
| [aws_eks_node_group.cpu_workers](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eks_node_group) | resource |
| [aws_eks_node_group.gpu_workers](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eks_node_group) | resource |
| [aws_iam_openid_connect_provider.cluster](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_openid_connect_provider) | resource |
| [aws_iam_policy.cluster_autoscaler](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_policy.ebs_csi](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_role.cluster](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.cluster_autoscaler](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.node](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.node_termination_handler](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy_attachment.cluster_AmazonEKSClusterPolicy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.cluster_AmazonEKSVPCResourceController](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.cluster_autoscaler](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.node_AmazonEC2ContainerRegistryReadOnly](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.node_AmazonEKSWorkerNodePolicy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.node_AmazonEKS_CNI_Policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.node_ebs_csi](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.node_termination_handler](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_kms_alias.eks](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_alias) | resource |
| [aws_kms_key.eks](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_key) | resource |
| [aws_launch_template.cpu_workers](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/launch_template) | resource |
| [aws_launch_template.gpu_workers](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/launch_template) | resource |
| [aws_security_group.node](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [aws_security_group_rule.node_ingress_self](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group_rule) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [tls_certificate.cluster](https://registry.terraform.io/providers/hashicorp/tls/latest/docs/data-sources/certificate) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_cluster_endpoint_public_access"></a> [cluster\_endpoint\_public\_access](#input\_cluster\_endpoint\_public\_access) | Enable public access to cluster endpoint | `bool` | `false` | no |
| <a name="input_cluster_name"></a> [cluster\_name](#input\_cluster\_name) | Name of the EKS cluster | `string` | `"ray-ml-cluster"` | no |
| <a name="input_commit_sha"></a> [commit\_sha](#input\_commit\_sha) | Git commit SHA for resource tagging | `string` | `"unknown"` | no |
| <a name="input_cpu_capacity_type"></a> [cpu\_capacity\_type](#input\_cpu\_capacity\_type) | Capacity type for CPU worker nodes (ON\_DEMAND or SPOT) | `string` | `"ON_DEMAND"` | no |
| <a name="input_cpu_node_desired_size"></a> [cpu\_node\_desired\_size](#input\_cpu\_node\_desired\_size) | Desired number of CPU worker nodes | `number` | `3` | no |
| <a name="input_cpu_node_instance_types"></a> [cpu\_node\_instance\_types](#input\_cpu\_node\_instance\_types) | Instance types for CPU worker nodes | `list(string)` | <pre>[<br/>  "m5.xlarge",<br/>  "m5.2xlarge"<br/>]</pre> | no |
| <a name="input_cpu_node_max_size"></a> [cpu\_node\_max\_size](#input\_cpu\_node\_max\_size) | Maximum number of CPU worker nodes | `number` | `10` | no |
| <a name="input_cpu_node_min_size"></a> [cpu\_node\_min\_size](#input\_cpu\_node\_min\_size) | Minimum number of CPU worker nodes | `number` | `2` | no |
| <a name="input_eks_addons"></a> [eks\_addons](#input\_eks\_addons) | Map of EKS addons to enable | `map(any)` | <pre>{<br/>  "coredns": {<br/>    "resolve_conflicts_on_create": "OVERWRITE",<br/>    "resolve_conflicts_on_update": "OVERWRITE"<br/>  },<br/>  "kube-proxy": {<br/>    "resolve_conflicts_on_create": "OVERWRITE",<br/>    "resolve_conflicts_on_update": "OVERWRITE"<br/>  },<br/>  "vpc-cni": {<br/>    "resolve_conflicts_on_create": "OVERWRITE",<br/>    "resolve_conflicts_on_update": "OVERWRITE"<br/>  }<br/>}</pre> | no |
| <a name="input_enable_cloudwatch_logs"></a> [enable\_cloudwatch\_logs](#input\_enable\_cloudwatch\_logs) | Enable CloudWatch logs for control plane | `bool` | `true` | no |
| <a name="input_enable_cluster_autoscaler"></a> [enable\_cluster\_autoscaler](#input\_enable\_cluster\_autoscaler) | Enable Kubernetes cluster autoscaler | `bool` | `true` | no |
| <a name="input_enable_ebs_csi_driver"></a> [enable\_ebs\_csi\_driver](#input\_enable\_ebs\_csi\_driver) | Enable EBS CSI driver for persistent volumes | `bool` | `true` | no |
| <a name="input_enable_gpu_nodes"></a> [enable\_gpu\_nodes](#input\_enable\_gpu\_nodes) | Enable GPU worker node pool | `bool` | `true` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | Environment name (dev, staging, production) | `string` | `"production"` | no |
| <a name="input_gpu_capacity_type"></a> [gpu\_capacity\_type](#input\_gpu\_capacity\_type) | Capacity type for GPU worker nodes (ON\_DEMAND or SPOT). Default is SPOT for cost optimization. | `string` | `"SPOT"` | no |
| <a name="input_gpu_node_desired_size"></a> [gpu\_node\_desired\_size](#input\_gpu\_node\_desired\_size) | Desired number of GPU worker nodes | `number` | `0` | no |
| <a name="input_gpu_node_instance_types"></a> [gpu\_node\_instance\_types](#input\_gpu\_node\_instance\_types) | Instance types for GPU worker nodes | `list(string)` | <pre>[<br/>  "g4dn.xlarge",<br/>  "g4dn.2xlarge"<br/>]</pre> | no |
| <a name="input_gpu_node_max_size"></a> [gpu\_node\_max\_size](#input\_gpu\_node\_max\_size) | Maximum number of GPU worker nodes | `number` | `5` | no |
| <a name="input_gpu_node_min_size"></a> [gpu\_node\_min\_size](#input\_gpu\_node\_min\_size) | Minimum number of GPU worker nodes | `number` | `0` | no |
| <a name="input_kms_key_arn"></a> [kms\_key\_arn](#input\_kms\_key\_arn) | The Amazon Resource Name (ARN) of the KMS key to use for envelope encryption of Kubernetes secrets. If not provided, a new key will be created. | `string` | `""` | no |
| <a name="input_kubernetes_version"></a> [kubernetes\_version](#input\_kubernetes\_version) | Kubernetes version for EKS | `string` | `"1.28"` | no |
| <a name="input_log_retention_days"></a> [log\_retention\_days](#input\_log\_retention\_days) | CloudWatch log retention in days | `number` | `7` | no |
| <a name="input_region"></a> [region](#input\_region) | AWS region for infrastructure deployment | `string` | `"us-east-1"` | no |
| <a name="input_repo_name"></a> [repo\_name](#input\_repo\_name) | GitHub repository name for resource tagging | `string` | `"unknown"` | no |
| <a name="input_subnet_ids"></a> [subnet\_ids](#input\_subnet\_ids) | List of subnet IDs to deploy the EKS cluster and worker nodes into (preferably private subnets) | `list(string)` | n/a | yes |
| <a name="input_tags"></a> [tags](#input\_tags) | Additional tags for all resources | `map(string)` | `{}` | no |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | ID of the existing VPC to deploy the EKS cluster into | `string` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_access_instructions"></a> [access\_instructions](#output\_access\_instructions) | Instructions to access the cluster |
| <a name="output_cloudwatch_log_group"></a> [cloudwatch\_log\_group](#output\_cloudwatch\_log\_group) | CloudWatch log group name |
| <a name="output_cluster_arn"></a> [cluster\_arn](#output\_cluster\_arn) | EKS cluster ARN |
| <a name="output_cluster_autoscaler_iam_role_arn"></a> [cluster\_autoscaler\_iam\_role\_arn](#output\_cluster\_autoscaler\_iam\_role\_arn) | IAM Role ARN for the Cluster Autoscaler (IRSA) |
| <a name="output_cluster_certificate_authority"></a> [cluster\_certificate\_authority](#output\_cluster\_certificate\_authority) | Cluster CA certificate |
| <a name="output_cluster_endpoint"></a> [cluster\_endpoint](#output\_cluster\_endpoint) | EKS cluster endpoint URL |
| <a name="output_cluster_iam_role_arn"></a> [cluster\_iam\_role\_arn](#output\_cluster\_iam\_role\_arn) | Cluster IAM role ARN |
| <a name="output_cluster_id"></a> [cluster\_id](#output\_cluster\_id) | EKS cluster ID |
| <a name="output_cluster_name"></a> [cluster\_name](#output\_cluster\_name) | EKS cluster name |
| <a name="output_cluster_oidc_issuer_url"></a> [cluster\_oidc\_issuer\_url](#output\_cluster\_oidc\_issuer\_url) | OIDC issuer URL for the cluster |
| <a name="output_cluster_security_group_id"></a> [cluster\_security\_group\_id](#output\_cluster\_security\_group\_id) | Cluster security group ID |
| <a name="output_cluster_version"></a> [cluster\_version](#output\_cluster\_version) | Kubernetes version |
| <a name="output_cpu_node_group_id"></a> [cpu\_node\_group\_id](#output\_cpu\_node\_group\_id) | CPU node group ID |
| <a name="output_cpu_node_group_status"></a> [cpu\_node\_group\_status](#output\_cpu\_node\_group\_status) | CPU node group status |
| <a name="output_estimated_monthly_cost"></a> [estimated\_monthly\_cost](#output\_estimated\_monthly\_cost) | Rough monthly cost estimate (USD) |
| <a name="output_gpu_node_group_id"></a> [gpu\_node\_group\_id](#output\_gpu\_node\_group\_id) | GPU node group ID |
| <a name="output_gpu_node_group_status"></a> [gpu\_node\_group\_status](#output\_gpu\_node\_group\_status) | GPU node group status |
| <a name="output_kubeconfig_command"></a> [kubeconfig\_command](#output\_kubeconfig\_command) | Command to configure kubectl |
| <a name="output_kubeconfig_path"></a> [kubeconfig\_path](#output\_kubeconfig\_path) | Suggested kubeconfig file path |
| <a name="output_node_iam_role_arn"></a> [node\_iam\_role\_arn](#output\_node\_iam\_role\_arn) | Node IAM role ARN |
| <a name="output_node_security_group_id"></a> [node\_security\_group\_id](#output\_node\_security\_group\_id) | Node security group ID |
| <a name="output_node_termination_handler_iam_role_arn"></a> [node\_termination\_handler\_iam\_role\_arn](#output\_node\_termination\_handler\_iam\_role\_arn) | IAM Role ARN for the AWS Node Termination Handler (IRSA) |
| <a name="output_region"></a> [region](#output\_region) | AWS region |
| <a name="output_resource_tags"></a> [resource\_tags](#output\_resource\_tags) | Tags applied to all resources |
<!-- END_TF_DOCS -->