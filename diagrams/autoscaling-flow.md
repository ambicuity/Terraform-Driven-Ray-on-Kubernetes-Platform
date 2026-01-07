# Autoscaling Flow

Multi-level autoscaling for cost-optimized ML workloads.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Workload Submitted                          │
│                                                                     │
│  User submits bursty_training.py to Ray cluster                    │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Level 1: Ray Autoscaler                          │
│                                                                     │
│  Monitors: Task queue depth, CPU/memory utilization                │
│  Decision: Need more workers?                                      │
│                                                                     │
│  IF queue_depth > threshold:                                        │
│    Request more Ray worker pods                                     │
└────────────────────┬────────────────────────────────────────────────┘
                     │ YES: Need capacity
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│              Level 2: Horizontal Pod Autoscaler (HPA)               │
│                                                                     │
│  Monitors: CPU/Memory metrics from Metrics Server                  │
│  Decision: Scale Ray worker pods?                                  │
│                                                                     │
│  IF avg_cpu > 70% OR avg_memory > 80%:                             │
│    Increase Ray worker pod replicas                                 │
│                                                                     │
│  Scaling Rules:                                                     │
│  • Scale up: Fast (30s stabilization)                              │
│  • Scale down: Slow (300s stabilization)                           │
│  • Max increase: 100% or 2 pods per 30s                            │
└────────────────────┬────────────────────────────────────────────────┘
                     │ Pods scheduled but...
                     │ No available nodes!
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│              Level 3: Cluster Autoscaler                            │
│                                                                     │
│  Monitors: Unschedulable pods (Pending state)                      │
│  Decision: Add EC2 nodes?                                          │
│                                                                     │
│  IF pods_pending > 0 AND pending_duration > 30s:                   │
│    Request new EC2 instances from Auto Scaling Group               │
│                                                                     │
│  Node Selection:                                                    │
│  • CPU pods → m5.xlarge nodes                                      │
│  • GPU pods → g4dn.xlarge nodes                                    │
│  • Respects taints/tolerations                                     │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   Level 4: AWS Auto Scaling                         │
│                                                                     │
│  Monitors: Desired capacity vs current capacity                    │
│  Action: Launch EC2 instances                                      │
│                                                                     │
│  Launch Process:                                                    │
│  1. Select AZ with least instances (balance)                       │
│  2. Launch from Launch Template                                    │
│  3. Bootstrap kubelet                                              │
│  4. Join cluster                                                   │
│  5. Mark node Ready                                                │
│                                                                     │
│  Duration: ~3-5 minutes                                            │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓ Node Ready
┌─────────────────────────────────────────────────────────────────────┐
│                  Pods Scheduled & Running                           │
│                                                                     │
│  Pending pods are now scheduled to new nodes                       │
│  Ray workers join cluster and process tasks                        │
└─────────────────────────────────────────────────────────────────────┘


                    SCALE DOWN FLOW
                    ===============

┌─────────────────────────────────────────────────────────────────────┐
│                      Workload Completes                             │
│                                                                     │
│  Task queue empty, low utilization detected                        │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓ (idle for 60s)
┌─────────────────────────────────────────────────────────────────────┐
│              Level 1: Ray Autoscaler                                │
│                                                                     │
│  IF queue_empty AND cpu_low:                                        │
│    Remove Ray worker pods                                           │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓ (wait 300s)
┌─────────────────────────────────────────────────────────────────────┐
│              Level 2: HPA Scale Down                                │
│                                                                     │
│  IF avg_cpu < 50% for 300s:                                         │
│    Reduce Ray worker replicas                                       │
│    (Max decrease: 50% per minute)                                  │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓ (wait 10 minutes)
┌─────────────────────────────────────────────────────────────────────┐
│              Level 3: Cluster Autoscaler                            │
│                                                                     │
│  IF node_utilization < 50% for 10 minutes:                         │
│    AND no non-DaemonSet pods on node:                              │
│    Drain and terminate node                                         │
│                                                                     │
│  Protection:                                                        │
│  • Never scale below min nodes (2 for CPU, 0 for GPU)             │
│  • Respect PodDisruptionBudgets                                    │
│  • Gradual scale-down (1 node at a time)                           │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     Steady State Reached                            │
│                                                                     │
│  Cluster at minimum size, ready for next burst                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Timing Summary

| Event | Layer | Typical Duration |
|-------|-------|-----------------|
| Task submitted | Ray | Immediate |
| Request more workers | Ray | 5-10 seconds |
| HPA scales pods | K8s | 30-60 seconds |
| Node needed | Cluster AS | Immediate detection |
| EC2 launched | AWS | 3-5 minutes |
| Node ready | K8s | 30-60 seconds |
| **Total scale-up** | | **4-7 minutes** |
| | | |
| Workload idle | Ray | 60 seconds |
| HPA scale down | K8s | 5 minutes |
| Node utilization low | Cluster AS | 10 minutes |
| Node terminated | AWS | 2-3 minutes |
| **Total scale-down** | | **15-20 minutes** |

## Cost Optimization

- **Scale-up**: Fast (4-7 min) to minimize queue time
- **Scale-down**: Gradual (15-20 min) to avoid thrashing
- **GPU nodes**: Start at 0, aggressive scale-down
- **CPU nodes**: Min 2 for base capacity

## Placeholder for Visual Diagram

An animated or multi-stage diagram showing:
1. Initial state (minimal resources)
2. Workload burst triggers scale-up
3. All three autoscalers coordinate
4. Peak capacity reached
5. Workload completes
6. Gradual scale-down
7. Return to minimal state

**Suggested format:** Animated GIF or step-by-step PNG sequence
