# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- replaced the custom Gemini CLI agent stack with CodeRabbit, Gemini Code Assist on GitHub, and official GitHub Agentic Workflows
- collapsed fragmented CI checks into one path-scoped required `CI` workflow
- updated assignment follow-up logic to suppress nudges when an assigned issue already has a linked open PR
- pinned public Terraform module examples to `v1.0.0`

### Removed

- legacy Gemini CLI subagents, setup action, queue files, and memory artifacts
- custom AI workflows (`gamma-triage`, `delta-executor`, `beta-reviewer`, `alpha-governor`, and related helpers)
- redundant standalone CI workflows that duplicated the required router

### Documentation

- rewrote automation, security, CI/CD, contribution, and roadmap docs to match the current repository model

## [v1.0.0] - 2026-02-26

### Added

- production-ready EKS and KubeRay Terraform platform
- Velero backup integration and KMS-backed security defaults
- OPA guardrails for infrastructure and Ray workloads
- Grafana dashboards and validation tooling

### Changed

- moved Terraform code into `terraform/`
- upgraded the EKS baseline to 1.31
- optimized CPU workers toward Graviton-based instance families

### Security

- defaulted the EKS public endpoint to `false`
- enforced KMS encryption for control-plane logs
- pinned GitHub Actions to stable version references
