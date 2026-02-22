# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Elite CI suite: Checkov, Infracost, terraform-docs, CodeQL, PR lint, stale bot
- OPA 1.0-compliant Rego policies with universal array comprehension syntax
- Terraform `mock_provider` support in test framework for offline validation
- AWS Node Termination Handler IAM for Spot interruption graceful draining

### Fixed
- OPA `rego_parse_error` caused by `some w in` inside array comprehensions
- Terraform test failure caused by missing explicit AWS provider credentials
- Duplicate `eks_addons` variable declaration in `variables.tf`

### Security
- Pinned all GitHub Actions to SHA or major-version tags
- EKS cluster endpoint public access defaulted to `false`
- KMS encryption enforced on CloudWatch log groups
