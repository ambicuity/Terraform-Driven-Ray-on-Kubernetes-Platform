# Operations Guide

## Prerequisites

- Terraform `>= 1.6.0`
- AWS CLI v2
- kubectl
- Helm 3
- Python 3.10+

The repo also bundles `.tmp-tools/bin/terraform-1.9.8` for local validation if your global Terraform is older.

## Deploy the Platform

For infrastructure only:

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

For the composed addon/workload stack:

```bash
cd terraform/examples/complete
terraform init
terraform plan
terraform apply
```

## Access the Cluster

```bash
aws eks update-kubeconfig --name <cluster-name> --region <region>
kubectl cluster-info
kubectl get nodes
```

## Verify the Addon Layer

If you used the complete example:

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=cluster-autoscaler
kubectl get pods -n ray-system
helm list -n ray-system
```

## Deploy the Ray Workload

If you are not using the complete example, install KubeRay and then deploy the local chart:

```bash
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm upgrade --install kuberay-operator kuberay/kuberay-operator -n ray-system --create-namespace
helm upgrade --install ray-cluster ./helm/ray -n ray-system
```

## Local Validation

```bash
make evidence
```

`make evidence` saves the bootstrap transcript, deterministic checks, supported-claim audit, and the chart-backed `./local_test.sh` run under `tests/evidence/`.

If you want to run only the quicker deterministic subset first:

```bash
make lint
make test
```

`local_test.sh` still deploys the real `helm/ray` chart on minikube and exercises the chart-backed path rather than a separate handwritten manifest.

## Troubleshooting

### Terraform tests say "No tests defined"

You are likely running Terraform `1.5.x`. Use Terraform `>= 1.6.0` or the bundled `.tmp-tools/bin/terraform-1.9.8`.

### GPU workloads stay pending after Spot reclamation

Check whether the platform was deployed with:

- `gpu_capacity_type = "SPOT"`
- `enable_gpu_ondemand_fallback = true`

If the fallback group is disabled, the cluster may have no reliable GPU landing zone after a Spot capacity loss.

### Nodes cannot pull images or reach AWS APIs

Ensure the worker nodes are in private subnets with functioning NAT or equivalent egress controls. The worker security group allows egress; the surrounding network still needs a real path out.
