# Terraform Module Reference

The root module in `terraform/` provisions the EKS platform. It intentionally does not deploy Helm workloads or Velero.

## Requirements

- Terraform `>= 1.6.0`
- AWS provider `>= 5.0`
- TLS provider `>= 4.0`

For local validation, the repository bundles `.tmp-tools/bin/terraform-1.9.8`.

## Important Inputs

Core:

- `cluster_name`
- `region`
- `vpc_id`
- `subnet_ids`
- `kubernetes_version`
- `enable_oidc_thumbprint_management`

CPU pool:

- `cpu_node_instance_types`
- `cpu_node_min_size`
- `cpu_node_desired_size`
- `cpu_node_max_size`
- `cpu_capacity_type`

GPU pool:

- `enable_gpu_nodes`
- `gpu_node_instance_types`
- `gpu_node_min_size`
- `gpu_node_desired_size`
- `gpu_node_max_size`
- `gpu_capacity_type`

GPU fallback:

- `enable_gpu_ondemand_fallback`
- `gpu_ondemand_fallback_instance_types`
- `gpu_ondemand_fallback_min_size`
- `gpu_ondemand_fallback_desired_size`
- `gpu_ondemand_fallback_max_size`

Platform features:

- `enable_cluster_autoscaler`
- `enable_ebs_csi_driver`
- `enable_cloudwatch_logs`
- `log_retention_days`
- `eks_addons`
- `tags`

Removed from the root module:

- `enable_velero`
- `velero_backup_schedule`
- Velero-specific outputs

Those concerns now live in `terraform/examples/complete/`.

## Important Outputs

- `cluster_name`
- `cluster_endpoint`
- `cluster_certificate_authority`
- `cluster_oidc_issuer_url`
- `oidc_provider_arn`
- `cpu_node_group_id`
- `gpu_node_group_id`
- `gpu_primary_node_group_id`
- `gpu_fallback_node_group_id`
- `cluster_autoscaler_iam_role_arn`
- `kubeconfig_command`

## Behavior Notes

- The root module attaches the documented launch templates to the EKS node groups.
- When `gpu_capacity_type = "SPOT"` and `enable_gpu_ondemand_fallback = true`, an additional On-Demand fallback GPU node group is created automatically.
- The module still creates EKS managed addons because they are platform infrastructure, not application workloads.
- Workload deployment belongs in `helm/ray/` or `terraform/examples/complete/`.

## Local Commands

```bash
make lint
make test
```

Or directly:

```bash
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform init -backend=false
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform validate
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform test
```
