# Contributing

## Principles

- Keep infrastructure changes in `terraform/`
- Keep workload changes in `helm/` or the example stack
- Preserve path-scoped CI behavior
- Do not reintroduce repo-owned autonomous bot workflows

## Local Validation

Preferred:

```bash
make lint
make test
```

Equivalent direct commands:

```bash
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform init -backend=false
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform validate
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform test
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform/examples/complete init -backend=false
./.tmp-tools/bin/terraform-1.9.8 -chdir=terraform/examples/complete validate
./.tmp-tools/bin/opa-0.63.0 test policies -v
helm lint helm/ray
helm template ray-ci helm/ray >/tmp/ray-rendered.yaml
actionlint -color
shellcheck local_test.sh validation/*.sh
python3 -m compileall scripts tests workloads validation
pytest tests -q
```

## Review Expectations

- Infrastructure-only changes should not claim to deploy workloads
- Spot GPU changes should keep the On-Demand fallback story explicit
- Docs should describe the root module as infra-only
- AI metadata is advisory only and should not become a merge gate
