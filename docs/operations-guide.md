# Operations Guide

Day-2 operations handbook for deploying, managing, and troubleshooting the Ray-on-EKS platform.

## Prerequisites

| Requirement | Minimum Version |
|-------------|----------------|
| Terraform | >= 1.6.0 |
| AWS CLI | v2 |
| kubectl | 1.28+ |
| Helm | 3.x |
| Python | 3.10+ (for workloads) |

**AWS Permissions**: The operator needs the ability to assume the IAM role used by Terraform (EKS, EC2, IAM, KMS, CloudWatch, S3, VPC).

---

## Deployment Lifecycle

### 1. Initial Setup

```bash
# Clone the repository
git clone https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform.git
cd Terraform-Driven-Ray-on-Kubernetes-Platform/examples/complete

# Initialize Terraform
terraform init

# Review the plan
terraform plan -out=tfplan

# Apply (creates VPC, EKS, node groups — ~15-20 minutes)
terraform apply tfplan
```

### 2. Access the Cluster

```bash
# Configure kubectl (command from Terraform output)
aws eks update-kubeconfig --name ray-ml-cluster --region us-east-1

# Verify access
kubectl cluster-info
kubectl get nodes
```

### 3. Verify Components

```bash
# Check node groups
kubectl get nodes -L ray.io/resource-type

# Check EKS addons
kubectl get pods -n kube-system

# Check Cluster Autoscaler
kubectl get pods -n kube-system -l app.kubernetes.io/name=cluster-autoscaler

# Check KubeRay Operator
kubectl get pods -n ray-system
```

### 4. Deploy Ray Cluster

If using the complete example with Helm integration, the KubeRay operator and Cluster Autoscaler are deployed automatically. To deploy a Ray cluster:

```bash
# Apply a RayCluster custom resource
kubectl apply -f - <<EOF
apiVersion: ray.io/v1alpha1
kind: RayCluster
metadata:
  name: ray-cluster
  namespace: ray-system
spec:
  headGroupSpec:
    rayStartParams:
      dashboard-host: '0.0.0.0'
    template:
      spec:
        containers:
          - name: ray-head
            image: rayproject/ray:2.9.0-py310
            resources:
              requests:
                cpu: "2"
                memory: "8Gi"
  workerGroupSpecs:
    - groupName: cpu-workers
      replicas: 2
      minReplicas: 2
      maxReplicas: 10
      rayStartParams: {}
      template:
        spec:
          containers:
            - name: ray-worker
              image: rayproject/ray:2.9.0-py310
              resources:
                requests:
                  cpu: "2"
                  memory: "4Gi"
EOF
```

### 5. Access the Ray Dashboard

```bash
kubectl port-forward -n ray-system svc/ray-cluster-head-svc 8265:8265
# Open http://localhost:8265
```

---

## Running the Bursty Workload

```bash
# Submit the workload to the Ray cluster
kubectl exec -it -n ray-system deploy/ray-cluster-head -- python /workloads/bursty_training.py

# Or run locally (if connected to Ray cluster)
RAY_ADDRESS=http://localhost:10001 python workloads/bursty_training.py
```

Monitor the 6-phase burst pattern in the Ray Dashboard. Watch the Cluster Autoscaler logs for node scaling:

```bash
kubectl logs -f -n kube-system -l app.kubernetes.io/name=cluster-autoscaler
```

---

## Monitoring

### CloudWatch Logs

Control plane logs are shipped to CloudWatch under the log group `/aws/eks/{cluster_name}/cluster`:

```bash
aws logs tail /aws/eks/ray-ml-cluster/cluster --follow
```

### Ray Dashboard Metrics

The Ray head node exposes Prometheus metrics at `:8265`. The Helm chart configures a `ServiceMonitor` for Prometheus scraping.

### Cost Tracking

Resources are tagged with:
- `ManagedBy: github-app`
- `Repository: {repo_name}`
- `Commit: {commit_sha}`
- `Environment: {environment}`

Use AWS Cost Explorer with these tag filters for cost attribution.

---

## Scaling Operations

### Manual Node Scaling

```bash
# Scale CPU node group (bypasses autoscaler temporarily)
aws eks update-nodegroup-config \
  --cluster-name ray-ml-cluster \
  --nodegroup-name ray-ml-cluster-cpu-workers \
  --scaling-config minSize=3,maxSize=15,desiredSize=5

# Scale GPU node group
aws eks update-nodegroup-config \
  --cluster-name ray-ml-cluster \
  --nodegroup-name ray-ml-cluster-gpu-workers \
  --scaling-config minSize=0,maxSize=8,desiredSize=2
```

> **Note**: The Terraform `lifecycle.ignore_changes` on `desired_size` prevents Terraform from reverting manual scaling changes.

### Drain a Node

```bash
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

---

## Teardown

### Terraform Destroy

```bash
# Plan the destruction
terraform plan -destroy -out=destroy.tfplan

# Execute (requires confirmation)
terraform apply destroy.tfplan
```

### Manual AWS Cleanup

Use the `aws-cleanup.yml` workflow for guided resource cleanup:

```bash
# Via GitHub Actions (manual dispatch)
gh workflow run aws-cleanup.yml
```

---

## Troubleshooting

### Nodes Not Joining Cluster

**Symptoms**: `kubectl get nodes` shows fewer nodes than expected.

**Checks**:
1. Verify node group status: `aws eks describe-nodegroup --cluster-name <name> --nodegroup-name <group>`
2. Check instance status: `aws ec2 describe-instances --filters "Name=tag:eks:cluster-name,Values=<name>"`
3. Check user-data execution: Connect to instance via SSM and check `/var/log/cloud-init-output.log`
4. Verify IAM role has required policies attached

### Pods Stuck in Pending

**Symptoms**: Pods remain in `Pending` state.

**Checks**:
1. `kubectl describe pod <name>` — Look for scheduling errors
2. Check if Cluster Autoscaler is running and has ASG permissions
3. Verify node group has capacity (`max_size` not reached)
4. For GPU pods: Verify toleration for `nvidia.com/gpu` taint

### Ray Workers Not Connecting

**Symptoms**: Ray head reports fewer workers than expected.

**Checks**:
1. Verify security group allows node-to-node communication (port 0-65535)
2. Check Ray head logs: `kubectl logs -n ray-system <head-pod>`
3. Check DNS resolution: `kubectl exec -it <pod> -- nslookup ray-cluster-head-svc`

### KMS Errors

**Symptoms**: `AccessDeniedException` on secret creation.

**Checks**:
1. Verify KMS key policy includes the EKS cluster role
2. Check key is not pending deletion: `aws kms describe-key --key-id <key-id>`
3. Verify key alias resolves: `aws kms describe-key --key-id alias/{cluster}-eks-secrets`

### Terraform State Lock

**Symptoms**: `Error acquiring the state lock`.

**Resolution**:
```bash
# Only after confirming no other Terraform process is running
terraform force-unlock <LOCK_ID>
```
