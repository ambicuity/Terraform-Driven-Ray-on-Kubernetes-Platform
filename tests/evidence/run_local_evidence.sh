#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

BOOTSTRAP_OUT="$SCRIPT_DIR/00-bootstrap.txt"
LINT_OUT="$SCRIPT_DIR/10-make-lint.txt"
TEST_OUT="$SCRIPT_DIR/20-make-test.txt"
CLAIMS_OUT="$SCRIPT_DIR/30-claims-audit.txt"
LOCAL_OUT="$SCRIPT_DIR/40-local-test.txt"
SUMMARY_OUT="$SCRIPT_DIR/SUMMARY.md"

STEP_NAMES=()
STEP_COMMANDS=()
STEP_FILES=()
STEP_STATUSES=()

strip_ansi() {
  python3 -c 'import re, sys; data = sys.stdin.read().replace("\r\n", "\n").replace("\r", "\n"); ansi = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]"); sys.stdout.write(ansi.sub("", data))'
}

run_step() {
  local label="$1"
  local outfile="$2"
  shift 2

  local cmd_display
  local status

  cmd_display="$(printf '%q ' "$@")"
  cmd_display="${cmd_display% }"

  printf '# %s\n# Command: %s\n\n' "$label" "$cmd_display" > "$outfile"

  set +e
  (
    cd "$REPO_ROOT"
    "$@"
  ) 2>&1 | strip_ansi >> "$outfile"
  status=${PIPESTATUS[0]}
  set -e

  printf '\n# Exit code: %s\n' "$status" >> "$outfile"

  STEP_NAMES+=("$label")
  STEP_COMMANDS+=("$cmd_display")
  STEP_FILES+=("$(basename "$outfile")")
  STEP_STATUSES+=("$status")

  return "$status"
}

write_summary() {
  local overall="PASS"
  local index
  local result

  for status in "${STEP_STATUSES[@]}"; do
    if [[ "$status" -ne 0 ]]; then
      overall="FAIL"
      break
    fi
  done

  # shellcheck disable=SC2016
  {
    printf '# Local Evidence Summary\n\n'
    printf 'This folder is the committed local proof bundle for the repository.\n\n'
    printf -- '- Claim inventory: [claim-matrix.md](claim-matrix.md)\n'
    printf -- '- Full workflow entrypoint: `make evidence`\n'
    printf -- '- Overall status: `%s`\n\n' "$overall"
    printf '| Step | Command | Result | Output |\n'
    printf '| --- | --- | --- | --- |\n'

    for index in "${!STEP_NAMES[@]}"; do
      if [[ "${STEP_STATUSES[$index]}" -eq 0 ]]; then
        result="PASS"
      else
        result="FAIL"
      fi

      printf '| %s | `%s` | `%s` | [%s](%s) |\n' \
        "${STEP_NAMES[$index]}" \
        "${STEP_COMMANDS[$index]}" \
        "$result" \
        "${STEP_FILES[$index]}" \
        "${STEP_FILES[$index]}"
    done

    printf '\n## Scope\n\n'
    printf -- '- Included in the committed local baseline: bootstrap, `make lint`, `make test`, supported-claim audit, and the chart-backed `./local_test.sh` run.\n'
    printf -- '- Extended live-cluster checks in `validation/` and workload stress scripts in `workloads/` stay available, but they are not marked as locally proven unless they are run and saved here.\n'
  } > "$SUMMARY_OUT"
}

failures=0

run_step "Bootstrap local prerequisites" "$BOOTSTRAP_OUT" bash tests/evidence/bootstrap_local.sh || failures=$((failures + 1))
run_step "Deterministic lint checks" "$LINT_OUT" make lint || failures=$((failures + 1))
run_step "Deterministic test checks" "$TEST_OUT" make test || failures=$((failures + 1))
run_step "Supported claims audit" "$CLAIMS_OUT" python3 tests/evidence/check_supported_claims.py || failures=$((failures + 1))
run_step "Chart-backed local cluster validation" "$LOCAL_OUT" ./local_test.sh || failures=$((failures + 1))

write_summary

if [[ "$failures" -ne 0 ]]; then
  printf 'Evidence workflow completed with %s failing step(s).\n' "$failures"
  exit 1
fi

printf 'Evidence workflow completed successfully.\n'
