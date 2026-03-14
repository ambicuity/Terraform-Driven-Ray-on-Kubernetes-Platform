# Local Evidence Summary

This folder is the committed local proof bundle for the repository.

- Claim inventory: [claim-matrix.md](claim-matrix.md)
- Full workflow entrypoint: `make evidence`
- Overall status: `PASS`

| Step | Command | Result | Output |
| --- | --- | --- | --- |
| Bootstrap local prerequisites | `bash tests/evidence/bootstrap_local.sh` | `PASS` | [00-bootstrap.txt](00-bootstrap.txt) |
| Deterministic lint checks | `make lint` | `PASS` | [10-make-lint.txt](10-make-lint.txt) |
| Deterministic test checks | `make test` | `PASS` | [20-make-test.txt](20-make-test.txt) |
| Supported claims audit | `python3 tests/evidence/check_supported_claims.py` | `PASS` | [30-claims-audit.txt](30-claims-audit.txt) |
| Chart-backed local cluster validation | `./local_test.sh` | `PASS` | [40-local-test.txt](40-local-test.txt) |

## Scope

- Included in the committed local baseline: bootstrap, `make lint`, `make test`, supported-claim audit, and the chart-backed `./local_test.sh` run.
- Extended live-cluster checks in `validation/` and workload stress scripts in `workloads/` stay available, but they are not marked as locally proven unless they are run and saved here.
