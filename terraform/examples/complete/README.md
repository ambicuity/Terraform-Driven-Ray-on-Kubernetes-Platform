# Complete Example

This example composes the infrastructure module with the addon/workload layer.

Included:

- VPC
- root EKS platform module
- Cluster Autoscaler Helm release
- KubeRay operator Helm release
- local `helm/ray` chart
- optional Velero

This is the place to look if you want to keep infrastructure and workload deployment in one stack while still keeping the reusable root module clean.

## Version Floor

- Terraform `>= 1.6.0`

## Validate

```bash
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform/examples/complete init -backend=false
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform/examples/complete validate
```
