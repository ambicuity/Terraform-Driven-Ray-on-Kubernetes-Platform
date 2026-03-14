# Terraform Module

This directory contains the reusable infrastructure module for the Ray-on-EKS platform.

## Scope

Included:

- EKS control plane
- IAM roles for the cluster and worker nodes
- KMS encryption for Kubernetes secrets
- CPU worker node group
- GPU worker node group
- optional On-Demand GPU fallback group for Spot-heavy clusters
- EKS managed addons
- OIDC and Cluster Autoscaler IRSA output

Not included:

- KubeRay operator deployment
- Ray workload deployment
- Velero

Those are composed in `terraform/examples/complete/`.

## Version Floor

- Terraform `>= 1.6.0`
- AWS provider `>= 5.0`
- TLS provider `>= 4.0`

## Safety Defaults

- CPU nodes default to `ON_DEMAND`
- GPU nodes default to `SPOT`
- Spot GPU mode defaults to creating an additional On-Demand fallback node group
- Node groups use attached launch templates with IMDSv2 and encrypted gp3 root volumes

## Useful Outputs

- `cluster_name`
- `cluster_endpoint`
- `cluster_certificate_authority`
- `cluster_oidc_issuer_url`
- `oidc_provider_arn`
- `cpu_node_group_id`
- `gpu_primary_node_group_id`
- `gpu_fallback_node_group_id`
- `cluster_autoscaler_iam_role_arn`

## Local Validation

```bash
make lint
make test
```

If your machine-wide Terraform is older than `1.6.0`, use the bundled binary:

```bash
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform init -backend=false
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform validate
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform test
```
