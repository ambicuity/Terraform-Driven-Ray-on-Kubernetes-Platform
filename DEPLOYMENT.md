# Deployment Guide

This document describes how to run the test suite locally, deploy the EKS cluster, and configure the remaining GitHub-side operations hooks.

---

## 1. Run Tests Locally (Single Command)

**Prerequisites:** Docker Desktop or Docker Engine.

```bash
# Build the image and run the full test suite with coverage output
make docker-test

# Or equivalently:
docker build -t ray-k8s-dev:local .
docker run --rm ray-k8s-dev:local
```

To run only the edge-case tests:

```bash
docker run --rm ray-k8s-dev:local pytest tests/test_edge_cases.py -v
```

To run linters:

```bash
make docker-lint
```

---

## 2. Run Tests Without Docker

**Prerequisites:** Python 3.11+.

```bash
pip install -r requirements-dev.txt
pytest tests/ -v --tb=short --cov=scripts --cov-report=term-missing
```

---

## 3. Optional GitHub-Side Secrets

Local development and test runs do not require repository secrets.

The only repository secrets used by the kept workflows are for optional scheduled drift detection:

| Variable | Description |
|---|---|
| `AWS_ROLE_ARN` | IAM role to assume through GitHub OIDC |
| `AWS_REGION` | AWS region for drift detection |

If these secrets are not configured, the `drift-detection.yml` workflow skips cleanly and exits green.

---

## 4. Provision EKS Infrastructure (Terraform)

> **Prerequisites:** AWS CLI configured, Terraform ≥ 1.6, an existing VPC with private subnets.

```bash
cd terraform

# 1. Initialise (configure your S3 backend in backend.tf if using remote state)
terraform init

# 2. Review the plan (no real resources created)
terraform plan \
  -var="vpc_id=vpc-0abc123456def" \
  -var='subnet_ids=["subnet-0abc1","subnet-0abc2"]' \
  -var="cluster_name=my-ray-cluster" \
  -out=tfplan

# 3. Apply (creates EKS cluster, ~15–20 minutes)
terraform apply tfplan
```

Key variables to configure:

| Variable | Default | Notes |
|---|---|---|
| `cluster_name` | `ray-ml-cluster` | Must be globally unique per AWS account |
| `vpc_id` | — | **Required**. Bring your own VPC |
| `subnet_ids` | — | **Required**. Private subnets recommended |
| `enable_gpu_nodes` | `true` | Set `false` to skip GPU node group (saves cost) |
| `gpu_capacity_type` | `SPOT` | Use `ON_DEMAND` for non-preemptible workloads |
| `gpu_node_min_size` | `0` | Scale-to-zero by default |

---

## 5. Configure kubectl

After `terraform apply` completes, the output `kubeconfig_command` gives you the exact command:

```bash
aws eks update-kubeconfig \
  --region us-east-1 \
  --name my-ray-cluster \
  --kubeconfig ~/.kube/ray-cluster.yaml

export KUBECONFIG=~/.kube/ray-cluster.yaml
kubectl get nodes
```

---

## 6. Deploy Ray Cluster via Helm

```bash
# Add KubeRay Helm repo
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo update

# Install the KubeRay Operator
helm install kuberay-operator kuberay/kuberay-operator \
  --namespace ray-system \
  --create-namespace \
  --version 1.1.1 \
  --wait

# Deploy the Ray Cluster using this repo's pre-configured values
helm install ray-cluster helm/ray/ \
  --namespace ray-system \
  --wait
```

Verify the cluster:

```bash
kubectl get raycluster -n ray-system
kubectl get pods -n ray-system

# Access Ray Dashboard (port-forward)
kubectl port-forward svc/ray-cluster-head-svc 8265:8265 -n ray-system &
open http://localhost:8265
```

---

## 7. Run a Bursty Workload

```bash
# Get the head pod name
HEAD=$(kubectl get pods -n ray-system -l ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}')

# Copy and run the bursty training workload
kubectl cp workloads/bursty_training.py ray-system/$HEAD:/tmp/
kubectl exec -n ray-system $HEAD -- python3 /tmp/bursty_training.py
```

---

## 8. Validate Resilience (Optional)

Run the validation scripts from the [Validation Runbook](validation/README.md):

```bash
# Prove HA Head Node failover (0% error rate during Spot interruption)
python3 workloads/ha_resilience_test.py

# Verify GPU pod density via prefix delegation
bash validation/test_gpu_density.sh

# Stress test object store spilling
python3 validation/test_memory_spill.py
```

---

## 9. Configure Ruleset Protection (Recommended)

The repository keeps the ruleset JSON in version control:

- `update_ruleset.json`
- `disable_ruleset.json`

The active ruleset should require only these checks on `main`:

- `CI Summary`
- `Secret Detection`
- `CodeQL Analyze (python)`

Apply the tracked ruleset with the GitHub CLI:

```bash
gh api \
  --method PUT \
  repos/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/rulesets/13113148 \
  --input update_ruleset.json
```

---

## 10. Tear Down

```bash
cd terraform
terraform destroy \
  -var="vpc_id=vpc-0abc123456def" \
  -var='subnet_ids=["subnet-0abc1","subnet-0abc2"]'
```

> **Warning:** This destroys all cluster resources permanently. Velero backups in S3 are retained per your S3 lifecycle policy.
