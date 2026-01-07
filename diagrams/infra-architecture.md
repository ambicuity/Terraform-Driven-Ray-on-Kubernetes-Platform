# Infrastructure Architecture

Complete end-to-end architecture from code to deployed infrastructure.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GitHub Repository                           │
│                                                                     │
│  ├── .github/workflows/        ← GitHub Actions orchestration      │
│  ├── terraform/                ← Infrastructure as Code            │
│  ├── helm/ray/                 ← Ray configuration                 │
│  ├── policies/                 ← OPA governance policies           │
│  └── workloads/                ← ML training jobs                  │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     │ Trigger: PR or Push
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      GitHub Actions                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ Terraform    │  │ Policy       │  │   Ray        │            │
│  │ Plan/Apply   │→ │ Validation   │→ │ Deployment   │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     │ Provision via Terraform
                     │
                     ↓
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
│  │  │  │  CPU Workers    │    │  GPU Workers    │     │     │   │
│  │  │  │                 │    │                 │     │     │   │
│  │  │  │ • m5.xlarge     │    │ • g4dn.xlarge   │     │     │   │
│  │  │  │ • Autoscaling   │    │ • Autoscaling   │     │     │   │
│  │  │  │ • 2-10 nodes    │    │ • 0-5 nodes     │     │     │   │
│  │  │  └─────────────────┘    └─────────────────┘     │     │   │
│  │  │                                                  │     │   │
│  │  │  ┌────────────────────────────────────────┐     │     │   │
│  │  │  │         Ray Cluster (Pods)             │     │     │   │
│  │  │  │                                        │     │     │   │
│  │  │  │  ┌──────────┐  ┌────────────────────┐  │     │     │   │
│  │  │  │  │ Ray Head │  │   Ray Workers      │  │     │     │   │
│  │  │  │  │          │  │  • CPU Workers     │  │     │     │   │
│  │  │  │  │ Dashboard│  │  • GPU Workers     │  │     │     │   │
│  │  │  │  │ Scheduler│  │  • Autoscaling     │  │     │     │   │
│  │  │  │  └──────────┘  └────────────────────┘  │     │     │   │
│  │  │  └────────────────────────────────────────┘     │     │   │
│  │  └──────────────────────────────────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Supporting Services                      │   │
│  │                                                            │   │
│  │  • S3 (Terraform state, Ray artifacts)                    │   │
│  │  • EBS (Persistent volumes)                               │   │
│  │  • CloudWatch (Logging & monitoring)                      │   │
│  │  • IAM (Roles & policies via OIDC)                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. **GitHub App Control Plane**
- Manages authentication via JWT → Installation tokens
- Orchestrates workflows (plan, apply, deploy, cost)
- No long-lived credentials

### 2. **Terraform Layer**
- Provisions EKS cluster with HA across 3 AZs
- Creates CPU and GPU node pools
- Configures networking (VPC, subnets, NAT)
- Manages IAM via OIDC integration

### 3. **Kubernetes Layer**
- EKS cluster running version 1.28
- Cluster autoscaler for node-level scaling
- EBS CSI driver for persistent storage
- Network policies for security

### 4. **Ray Layer**
- KubeRay operator for cluster management
- Ray head node (persistent, single replica)
- CPU workers (2-10 replicas, autoscaling)
- GPU workers (0-5 replicas, tainted nodes)
- Horizontal Pod Autoscaler

### 5. **Policy Layer**
- OPA policies enforce:
  - Max node counts
  - Instance type restrictions
  - Required encryption
  - Resource tagging
  - Cost controls

## Data Flow

```
Developer → PR → Plan → Review → Merge → Apply → Deploy → Scale
    ↓
  Policy Check
    ↓
  Cost Analysis
    ↓
  Daily Reports
```

## Placeholder for Visual Diagram

A detailed architectural diagram will be added here showing:
- AWS VPC layout with subnets
- EKS control plane and worker nodes
- Ray cluster components
- Autoscaling relationships
- Security boundaries

**File format:** PNG or SVG for best clarity
