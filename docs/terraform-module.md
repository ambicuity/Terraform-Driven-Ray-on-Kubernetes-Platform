# Terraform Module Reference

Complete reference for the `Terraform-Driven-Ray-on-Kubernetes-Platform` module.

## Provider Requirements

| Provider | Source | Version |
|----------|--------|---------|
| `aws` | `hashicorp/aws` | `>= 5.0` |
| `tls` | `hashicorp/tls` | `>= 4.0` |
| `kubernetes` | `hashicorp/kubernetes` | `>= 2.0` |

**Terraform**: `>= 1.6.0`

## File Structure

| File | Purpose |
|------|---------|
| `main.tf` | Core resources — EKS cluster, IAM roles, KMS, OIDC, security groups, CloudWatch, EKS addons |
| `node_pools.tf` | CPU/GPU node groups, launch templates, Cluster Autoscaler IAM, Node Termination Handler |
| `variables.tf` | All input variables with validation rules |
| `outputs.tf` | All module outputs |
| `versions.tf` | Terraform and provider version constraints |
| `user-data.sh` | CPU node bootstrap script (kubelet + CloudWatch agent) |
| `user-data-gpu.sh` | GPU node bootstrap script (kubelet + NVIDIA drivers + container runtime) |

## Inputs

### Core Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `region` | `string` | `"us-east-1"` | AWS region |
| `environment` | `string` | `"production"` | Environment name. Must be `dev`, `staging`, or `production` |
| `cluster_name` | `string` | `"ray-ml-cluster"` | EKS cluster name |
| `repo_name` | `string` | `"unknown"` | GitHub repo name for resource tagging |
| `commit_sha` | `string` | `"unknown"` | Git commit SHA for resource tagging |

### Networking (Required)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `vpc_id` | `string` | — | **Required.** ID of existing VPC |
| `subnet_ids` | `list(string)` | — | **Required.** Subnet IDs (preferably private) |

### EKS Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `kubernetes_version` | `string` | `"1.28"` | Kubernetes version |
| `kms_key_arn` | `string` | `""` | KMS key ARN for secret encryption. Empty → creates new key |
| `cluster_endpoint_public_access` | `bool` | `false` | Enable public endpoint access |
| `eks_addons` | `map(any)` | vpc-cni, kube-proxy, coredns | EKS managed addons |

### CPU Node Pool

| Variable | Type | Default | Validation |
|----------|------|---------|------------|
| `cpu_node_instance_types` | `list(string)` | `["m5.xlarge", "m5.2xlarge"]` | — |
| `cpu_node_min_size` | `number` | `2` | 1–10 |
| `cpu_node_max_size` | `number` | `10` | 1–20 |
| `cpu_node_desired_size` | `number` | `3` | — |
| `cpu_capacity_type` | `string` | `"ON_DEMAND"` | `ON_DEMAND` or `SPOT` |

### GPU Node Pool

| Variable | Type | Default | Validation |
|----------|------|---------|------------|
| `enable_gpu_nodes` | `bool` | `true` | — |
| `gpu_node_instance_types` | `list(string)` | `["g4dn.xlarge", "g4dn.2xlarge"]` | — |
| `gpu_node_min_size` | `number` | `0` | 0–5 |
| `gpu_node_max_size` | `number` | `5` | 0–10 |
| `gpu_node_desired_size` | `number` | `0` | — |
| `gpu_capacity_type` | `string` | `"SPOT"` | `ON_DEMAND` or `SPOT` |

### Features

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `enable_ebs_csi_driver` | `bool` | `true` | Attach EBS CSI IAM policy to node role |
| `enable_cluster_autoscaler` | `bool` | `true` | Create Cluster Autoscaler IRSA role |
| `enable_cloudwatch_logs` | `bool` | `true` | Ship control plane logs to CloudWatch |
| `log_retention_days` | `number` | `7` | CloudWatch log retention |
| `tags` | `map(string)` | `{}` | Additional tags for all resources |

## Outputs

### Cluster

| Output | Description | Sensitive |
|--------|-------------|-----------|
| `cluster_id` | EKS cluster ID | No |
| `cluster_name` | EKS cluster name | No |
| `cluster_endpoint` | API server endpoint URL | No |
| `cluster_version` | Kubernetes version | No |
| `cluster_arn` | Cluster ARN | No |
| `cluster_certificate_authority` | Base64-encoded CA cert | **Yes** |
| `cluster_oidc_issuer_url` | OIDC issuer URL | No |

### Access

| Output | Description |
|--------|-------------|
| `kubeconfig_command` | `aws eks update-kubeconfig ...` command |
| `kubeconfig_path` | Suggested kubeconfig file path |
| `access_instructions` | Step-by-step cluster access guide |

### Node Groups

| Output | Description |
|--------|-------------|
| `cpu_node_group_id` | CPU node group ID |
| `cpu_node_group_status` | CPU node group health status |
| `gpu_node_group_id` | GPU node group ID (null if disabled) |
| `gpu_node_group_status` | GPU node group health status |

### Security

| Output | Description |
|--------|-------------|
| `cluster_security_group_id` | EKS-managed cluster SG |
| `node_security_group_id` | Custom node SG |
| `cluster_iam_role_arn` | Cluster service role ARN |
| `node_iam_role_arn` | Node instance role ARN |
| `cluster_autoscaler_iam_role_arn` | IRSA role for Cluster Autoscaler |
| `node_termination_handler_iam_role_arn` | IRSA role for NTH (Spot only) |

### Monitoring & Cost

| Output | Description |
|--------|-------------|
| `cloudwatch_log_group` | Log group name |
| `region` | Deployed region |
| `resource_tags` | Merged tag map |
| `estimated_monthly_cost` | Approximate cost string |

## Usage Examples

### Minimal

```hcl
module "ray_eks_cluster" {
  source = "github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform"

  cluster_name = "my-ray-cluster"
  region       = "us-east-1"
  vpc_id       = "vpc-0abcd1234efgh5678"
  subnet_ids   = ["subnet-aaa", "subnet-bbb"]
}
```

### Production with GPU

```hcl
module "ray_eks_cluster" {
  source = "github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform"

  cluster_name = "prod-ray-cluster"
  region       = "us-east-1"
  environment  = "production"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cpu_node_min_size     = 2
  cpu_node_max_size     = 10
  cpu_node_desired_size = 3

  enable_gpu_nodes      = true
  gpu_node_min_size     = 0
  gpu_node_max_size     = 5
  gpu_node_desired_size = 0
  gpu_capacity_type     = "SPOT"

  tags = {
    Team    = "ml-platform"
    CostCenter = "engineering"
  }
}
```

### Complete Example with Helm

See [`examples/complete/`](../terraform/examples/complete/) for a fully runnable deployment that includes:
- VPC provisioning via `terraform-aws-modules/vpc/aws`
- Cluster Autoscaler Helm chart
- KubeRay Operator Helm chart

## Testing

The module includes a native Terraform test at `terraform/tests/module.tftest.hcl` using `mock_provider` for offline validation:

```bash
terraform test
```

This validates:
- Cluster name propagation
- CPU nodes default to `ON_DEMAND`
- GPU nodes default to `SPOT`
