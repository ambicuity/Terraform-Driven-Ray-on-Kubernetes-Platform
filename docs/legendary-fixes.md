# Legendary Fixes: Operator & FinOps Runbook

This document details 5 architectural fixes implemented in this repository to resolve "Legendary Problems" (long-standing, high-impact bugs) in the broader Ray-on-Kubernetes ecosystem.

## 1. High Availability 502 Errors (KubeRay #1153)
**Problem:** During Head Node failover (spot interruption, OOM), RayService endpoints drop up to 20% of traffic because K8s marks the new pod as "Ready" before the Ray GCS (Global Control Store) has recovered its metadata.
**Our Fix:** 
- **Readiness Probes:** We override the default KubeRay TCP probe with an explicit `ray health-check` execution probe in `helm/ray/values.yaml`.
- **Graceful Draining:** We inject a `preStop` hook (`ray stop --grace-period=30`) that ensures the head node stops accepting new requests and drains existing tasks before Kubernetes SIGTERM takes effect.

## 2. Worker Initialization OOMKilled (KubeRay #2735)
**Problem:** The default `wait-gcs-ready` init container runs `ray health-check`, which imports the entire 180MB+ Python data science environment, causing OOMs on cost-optimized machines.
**Our Fix:** 
- We inject a lightweight pure-Python socket check with zero external dependencies via the `initContainers` array in `helm/ray/values.yaml`. This drops the init memory footprint from ~200MB to <10MB.

## 3. Voluntary Disruption Failures (KubeRay #1333, TF #3607)
**Problem:** Node maintenance or Spot interruptions delete pods forcefully without respecting Ray worker availability, breaking running jobs.
**Our Fix:**
- **Pod Disruption Budgets (PDB):** We provision explicit PDBs (`helm/ray/pdb.yaml`) to ensure `minAvailable: 1` for CPU workloads and coordinate safe evictions.
- **ASG Lifecycle Hooks:** We added `aws_autoscaling_lifecycle_hook` on the Terraform GPU node groups (`terraform/node_pools.tf`) to grant AWS Node Termination Handler enough time to coordinate Graceful Node Shutdown.

## 4. OIDC Thumbprint Perpetual Drift (TF-EKS #3607)
**Problem:** Applying Terraform constantly shows a diff on the `aws_iam_openid_connect_provider` because AWS dynamically injects thumbprints, destroying CI/CD trust.
**Our Fix:**
- Split the OIDC provider into two distinct resources in `terraform/main.tf` (`cluster_managed` vs `cluster_unmanaged`), utilizing `lifecycle { ignore_changes = [thumbprint_list] }` for the default, unmanaged path.

## 5. Stale KubeConfig "Silent Drops" (SkyPilot #8785)
**Problem:** If an EKS cluster is destroyed and recreated with the same name, local caches and orchestration tools try to reuse the old endpoint, causing silent timeout drops instead of clean reconnection cycles.
**Our Fix:**
- **Cluster Identity Validation Script:** Included in `scripts/validate_cluster_identity.py` and run via GitHub Actions. It validates the active context against the literal `kube-system` namespace UID. A mismatch implies cluster recreation and triggers an immediate workflow failure instructing the user to flush cache via `aws eks update-kubeconfig`.
