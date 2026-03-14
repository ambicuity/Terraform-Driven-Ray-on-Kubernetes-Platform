#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

say() {
  printf '%s\n' "$*"
}

require_brew() {
  if ! command -v brew >/dev/null 2>&1; then
    say "Homebrew is required for the local evidence workflow on macOS."
    exit 1
  fi
}

ensure_brew_package() {
  local pkg="$1"
  local cmd="${2:-$1}"

  if command -v "$cmd" >/dev/null 2>&1; then
    say "[ok] $pkg available at $(command -v "$cmd")"
    return
  fi

  say "[install] brew install $pkg"
  brew install "$pkg"
  say "[ok] $pkg installed"
}

ensure_or_note_bundled_binary() {
  local name="$1"
  local bundled_path="$2"
  local brew_pkg="${3:-$1}"

  if [[ -x "$bundled_path" ]]; then
    say "[ok] using bundled $name at ${bundled_path#"$REPO_ROOT"/}"
    return
  fi

  if command -v "$name" >/dev/null 2>&1; then
    say "[ok] $name available at $(command -v "$name")"
    return
  fi

  say "[install] brew install $brew_pkg"
  brew install "$brew_pkg"
  say "[ok] $name installed"
}

print_version() {
  local label="$1"
  shift

  if "$@" >/dev/null 2>&1; then
    say "[version] $label: $("$@" 2>/dev/null | head -n 1)"
  fi
}

say "Preparing local prerequisites for the committed evidence workflow"
say "Repository root: $REPO_ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  say "This bootstrap script targets macOS/Homebrew. Continuing in best-effort mode."
fi

require_brew

ensure_brew_package python3 python3
ensure_brew_package helm helm
ensure_brew_package kubectl kubectl
ensure_brew_package minikube minikube
ensure_brew_package actionlint actionlint
ensure_brew_package shellcheck shellcheck
ensure_brew_package colima colima
ensure_brew_package docker docker

TERRAFORM_BIN="$REPO_ROOT/.tmp-tools/bin/terraform-1.9.8"
OPA_BIN="$REPO_ROOT/.tmp-tools/bin/opa-0.63.0"

ensure_or_note_bundled_binary terraform "$TERRAFORM_BIN" terraform
ensure_or_note_bundled_binary opa "$OPA_BIN" opa

print_version "python3" python3 --version
print_version "helm" helm version --short
print_version "kubectl" kubectl version --client=true --output=yaml
print_version "minikube" minikube version
print_version "actionlint" actionlint -version
print_version "shellcheck" shellcheck --version

if [[ -x "$TERRAFORM_BIN" ]]; then
  print_version "bundled terraform" "$TERRAFORM_BIN" version
elif command -v terraform >/dev/null 2>&1; then
  print_version "terraform" terraform version
else
  say "[error] terraform is not available"
fi

if [[ -x "$OPA_BIN" ]]; then
  print_version "bundled opa" "$OPA_BIN" version
elif command -v opa >/dev/null 2>&1; then
  print_version "opa" opa version
else
  say "[error] opa is not available"
fi

if command -v colima >/dev/null 2>&1; then
  if colima status >/dev/null 2>&1; then
    say "[ok] colima is already running"
  else
    say "[note] colima is installed but not running; local_test.sh will start it if needed"
  fi
fi

say "Bootstrap complete."
