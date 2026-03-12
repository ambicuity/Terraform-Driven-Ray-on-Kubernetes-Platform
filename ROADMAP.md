# ROADMAP.md — Terraform-Driven Ray on Kubernetes Platform

## Current Version: v1.0.0

## Milestone 1 — Production Core

| Feature | Status |
|---|---|
| EKS cluster Terraform module | Done |
| KubeRay Helm deployment | Done |
| GPU node groups with Spot and prefix delegation | Done |
| Velero backup integration | Done |
| OPA guardrails | Done |
| Ray HA and GCS stability fixes | Done |
| Grafana dashboards | Done |

## Milestone 2 — Repository Automation Hardening

| Feature | Status |
|---|---|
| Path-scoped required CI router | Done |
| Official GitHub Agentic Workflows (`gh-aw`) | Done |
| CodeRabbit integration | Done |
| Gemini Code Assist on GitHub integration | Done |
| Slash-command workflow for assignment and status management | Done |
| Assignment follow-up with linked-PR detection | Done |
| Terraform source pinning to `v1.0.0` in docs | Done |
| Removal of custom Gemini CLI agent runtime | Done |

## Milestone 3 — Production Readiness Follow-Through

| Feature | Status |
|---|---|
| Further separation of infra and workload delivery concerns | Planned |
| Branch protection and required-check cleanup | Planned |
| Release automation aligned to pinned tags | Planned |
| Additional workload validation depth | Planned |

## Milestone 4 — Multi-Cloud and Advanced MLOps

| Feature | Status |
|---|---|
| GKE support via provider abstraction | Planned |
| AKS support | Planned |
| Ray Serve integration and ingress templates | Planned |
| Automated canary deploys for Ray workloads | Planned |
| Per-job cost attribution tags | Planned |

## Version History

| Version | Date | Summary |
|---|---|---|
| v1.0.0 | 2026-02-26 | Production-ready EKS and KubeRay platform baseline |
