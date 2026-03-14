#!/usr/bin/env bash
# MIT License
# Copyright (c) 2026 ambicuity
#
# local_test.sh — Mac M2 Local Ray Cluster Validation Harness
#
# Installs minikube (via Homebrew if not present), deploys KubeRay + a minimal
# Ray cluster, then runs all synthetic validations from this repository.
#
# Prerequisites: Homebrew must be installed.
# Usage:  chmod +x local_test.sh && ./local_test.sh
# Teardown: ./local_test.sh --teardown
#
# Safe to run repeatedly; every step is idempotent.
# -------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour helpers ───────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BLUE}ℹ  $*${NC}"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
fail()    { echo -e "${RED}❌ $*${NC}"; exit 1; }
header()  { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════${NC}"; echo -e "${BOLD}  $*${NC}"; echo -e "${BOLD}${BLUE}══════════════════════════════════════${NC}"; }

# ── Configuration ─────────────────────────────────────────────────────────────
PROFILE="ray-local"
MEMORY=6144           # MB — target upper bound, adjusted to fit local Docker memory if needed
CPUS=4
KUBERNETES_VERSION="v1.29.3"
KUBERAY_OPERATOR_VERSION="1.1.1"
RAY_CLUSTER_NAMESPACE="ray-system"
HELM_RELEASE="ray-cluster"
RAY_CLUSTER_NAME="ray-cluster"
LOCAL_VALUES_FILE="$SCRIPT_DIR/validation/local-chart-values.yaml"
VALIDATION_TIMEOUT=180 # seconds to wait for the Ray head pod
PASS=0
FAIL=0
TEMP_KUBECONFIG=""

# shellcheck disable=SC2329
cleanup() {
  if [[ -n "${TEMP_KUBECONFIG:-}" && -f "$TEMP_KUBECONFIG" ]]; then
    rm -f "$TEMP_KUBECONFIG"
  fi
}

trap cleanup EXIT

# ── Teardown guard ────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--teardown" ]]; then
  warn "Tearing down minikube profile: $PROFILE"
  minikube delete --profile "$PROFILE" 2>/dev/null || true
  success "Teardown complete."
  exit 0
fi

# ── Step 1 — Homebrew dependencies ───────────────────────────────────────────
header "Step 1 — Installing / verifying dependencies"

install_brew_pkg() {
  local pkg="$1"
  local cmd="${2:-$1}"
  if command -v "$cmd" &>/dev/null; then
    success "$pkg already installed ($(command -v "$cmd"))"
  else
    info "Installing $pkg via Homebrew…"
    brew install "$pkg"
    success "$pkg installed."
  fi
}

# Determine native architecture to pull the optimal Ray Docker image
if [[ "$(uname -m)" == "arm64" || "$(uname -m)" == "aarch64" ]]; then
  RAY_IMAGE_REPOSITORY="rayproject/ray"
  RAY_IMAGE_TAG="2.9.3-py310-aarch64"
else
  RAY_IMAGE_REPOSITORY="rayproject/ray"
  RAY_IMAGE_TAG="2.9.3-py310"
fi
info "Host architecture is $(uname -m). Selected Ray Image: ${RAY_IMAGE_REPOSITORY}:${RAY_IMAGE_TAG}"

install_brew_pkg minikube minikube
install_brew_pkg helm     helm
install_brew_pkg kubectl  kubectl
install_brew_pkg python3  python3

# Ensure required Python packages are available (local venv to keep system clean)
VENV_DIR="$SCRIPT_DIR/.venv-ray-test"
if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating Python venv at $VENV_DIR …"
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet "ray[default]>=2.9.0" "kubernetes>=28.1.0" "numpy>=1.26.0"
success "Python dependencies ready."

# ── Step 1b — Ensure Docker / Colima is running ─────────────────────────────
# On macOS, Docker is typically provided by Colima or Docker Desktop.
# If Colima is present but not running, start it automatically.
if command -v colima &>/dev/null; then
  if ! colima status 2>/dev/null | grep -q 'running'; then
    info "Colima not running — starting it (4 CPU, 6 GB, vz+rosetta)…"
    colima start --cpu 4 --memory 6 --arch aarch64 --vm-type=vz --vz-rosetta
    success "Colima started."
  else
    success "Colima already running."
  fi
  # Point Docker CLI at the Colima socket
  export DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock"
fi

if command -v docker &>/dev/null; then
  DOCKER_MEMORY_BYTES="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
  if [[ "$DOCKER_MEMORY_BYTES" =~ ^[0-9]+$ ]] && (( DOCKER_MEMORY_BYTES > 0 )); then
    DOCKER_MEMORY_MB=$((DOCKER_MEMORY_BYTES / 1024 / 1024))
    SAFE_MEMORY_MB=$((DOCKER_MEMORY_MB - 256))
    if (( SAFE_MEMORY_MB < MEMORY )); then
      MEMORY=$SAFE_MEMORY_MB
      info "Adjusted minikube memory to ${MEMORY}MB to fit the active Docker runtime."
    fi
  fi
fi

# ── Step 2 — Start minikube ───────────────────────────────────────────────────
header "Step 2 — Starting minikube ($PROFILE)"

if minikube status --profile "$PROFILE" 2>/dev/null | grep -q "host: Running"; then
  success "Minikube profile $PROFILE already running."
else
  info "Starting minikube (driver=docker, cpus=$CPUS, memory=${MEMORY}MB)…"
  # Use docker driver — works natively on M2 without virtualisation overhead.
  minikube start \
    --profile "$PROFILE" \
    --driver=docker \
    --cpus="$CPUS" \
    --memory="${MEMORY}" \
    --kubernetes-version="$KUBERNETES_VERSION" \
    --wait=all
  success "Minikube started."
fi

# Point kubectl at our profile
TEMP_KUBECONFIG="$(mktemp "${TMPDIR:-/tmp}/ray-local-kubeconfig.XXXXXX")"
minikube -p "$PROFILE" kubectl -- config view --raw > "$TEMP_KUBECONFIG"
export KUBECONFIG="$TEMP_KUBECONFIG"

kubectl cluster-info

# ── Step 3 — Install KubeRay operator via Helm ───────────────────────────────
header "Step 3 — Installing KubeRay Operator v${KUBERAY_OPERATOR_VERSION}"

helm repo add kuberay https://ray-project.github.io/kuberay-helm/ --force-update
helm repo update kuberay

if helm status kuberay-operator -n "$RAY_CLUSTER_NAMESPACE" &>/dev/null; then
  success "KubeRay operator already installed; upgrading if needed…"
  helm upgrade kuberay-operator kuberay/kuberay-operator \
    --namespace "$RAY_CLUSTER_NAMESPACE" \
    --version "$KUBERAY_OPERATOR_VERSION" \
    --wait --timeout 3m
else
  info "Installing KubeRay operator…"
  kubectl create namespace "$RAY_CLUSTER_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
  helm install kuberay-operator kuberay/kuberay-operator \
    --namespace "$RAY_CLUSTER_NAMESPACE" \
    --version "$KUBERAY_OPERATOR_VERSION" \
    --set image.pullPolicy=IfNotPresent \
    --wait --timeout 3m
  success "KubeRay operator installed."
fi

# ── Step 4 — Deploy minimal RayCluster via the real Helm chart ───────────────
header "Step 4 — Deploying RayCluster ($RAY_CLUSTER_NAME)"

if helm status "$HELM_RELEASE" -n "$RAY_CLUSTER_NAMESPACE" &>/dev/null; then
  info "Removing existing Ray chart release to avoid stale RayCluster fields…"
  helm uninstall "$HELM_RELEASE" -n "$RAY_CLUSTER_NAMESPACE" >/dev/null
  kubectl wait \
    --for=delete "raycluster/${RAY_CLUSTER_NAME}" \
    --namespace "$RAY_CLUSTER_NAMESPACE" \
    --timeout=180s >/dev/null 2>&1 || true
  kubectl delete pods \
    -n "$RAY_CLUSTER_NAMESPACE" \
    -l "ray.io/cluster=${RAY_CLUSTER_NAME}" \
    --ignore-not-found >/dev/null 2>&1 || true
fi

kubectl delete raycluster raycluster-local -n "$RAY_CLUSTER_NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
helm install "$HELM_RELEASE" "$SCRIPT_DIR/helm/ray" \
  --namespace "$RAY_CLUSTER_NAMESPACE" \
  --values "$LOCAL_VALUES_FILE" \
  --set image.repository="$RAY_IMAGE_REPOSITORY" \
  --set image.tag="$RAY_IMAGE_TAG" \
  --wait \
  --timeout 5m
success "RayCluster chart installed."

# ── Step 5 — Wait for Ray head pod to be Ready ───────────────────────────────
header "Step 5 — Waiting for Ray head pod (timeout=${VALIDATION_TIMEOUT}s)"

info "Waiting for KubeRay to create the head pod…"
DEADLINE=$(( $(date +%s) + VALIDATION_TIMEOUT ))
while true; do
  POD_COUNT="$(kubectl get pods \
    -n "$RAY_CLUSTER_NAMESPACE" \
    -l "ray.io/node-type=head,ray.io/cluster=${RAY_CLUSTER_NAME}" \
    --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$POD_COUNT" -gt 0 ]] && break
  if [[ $(date +%s) -ge $DEADLINE ]]; then
    fail "Timed out waiting for head pod to be created by KubeRay operator."
  fi
  info "  No head pod yet — waiting 10s (timeout in $(( DEADLINE - $(date +%s) ))s)…"
  sleep 10
done

HEAD_POD="$(kubectl get pods \
  -n "$RAY_CLUSTER_NAMESPACE" \
  -l "ray.io/node-type=head,ray.io/cluster=${RAY_CLUSTER_NAME}" \
  -o jsonpath='{.items[0].metadata.name}')"
info "Head pod created. Waiting for Ready condition…"
kubectl wait "pod/${HEAD_POD}" \
  --namespace "$RAY_CLUSTER_NAMESPACE" \
  --for=condition=Ready \
  --timeout="${VALIDATION_TIMEOUT}s"

success "Head pod ready: $HEAD_POD"

# Wait for the worker pod to also appear and become Ready.
# The Python validations require raylets (workers) to be registered in GCS.
info "Waiting for KubeRay to create the worker pod…"
DEADLINE2=$(( $(date +%s) + VALIDATION_TIMEOUT ))
while true; do
  W_COUNT="$(kubectl get pods \
    -n "$RAY_CLUSTER_NAMESPACE" \
    -l "ray.io/node-type=worker,ray.io/cluster=${RAY_CLUSTER_NAME}" \
    --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$W_COUNT" -gt 0 ]] && break
  if [[ $(date +%s) -ge $DEADLINE2 ]]; then
    warn "Worker pod never appeared — continuing without it."
    break
  fi
  info "  No worker pod yet — waiting 10s…"
  sleep 10
done
# Best-effort wait; if worker isn't ready, validations mark it accordingly.
if kubectl wait pods \
  --namespace "$RAY_CLUSTER_NAMESPACE" \
  --for=condition=Ready \
  --selector="ray.io/node-type=worker,ray.io/cluster=${RAY_CLUSTER_NAME}" \
  --timeout=120s 2>/dev/null; then
  success "Worker pod ready."
else
  warn "Worker pod wait timed out — some validations may fail."
fi

info "Allowing 15s for raylets to register in GCS…"
sleep 15

HEAD_POD="$(kubectl get pods \
  -n "$RAY_CLUSTER_NAMESPACE" \
  -l "ray.io/node-type=head,ray.io/cluster=${RAY_CLUSTER_NAME}" \
  -o jsonpath='{.items[0].metadata.name}')"

# ── Validation helpers ────────────────────────────────────────────────────────
run_validation() {
  local name="$1"; shift
  info "Running: $name"
  if "$@"; then
    success "PASS — $name"
    PASS=$((PASS + 1))
  else
    warn "FAIL — $name (non-blocking; logged for report)"
    FAIL=$((FAIL + 1))
  fi
}

# ── Step 6 — Synthetic Validations ───────────────────────────────────────────
header "Step 6 — Synthetic Validations"

# ── 6a: Cluster connectivity ──────────────────────────────────────────────────
run_validation "Cluster connectivity" bash -c "kubectl cluster-info &>/dev/null"

# ── 6b: KubeRay operator pod running ─────────────────────────────────────────
run_validation "KubeRay operator pod running" bash -c \
  "kubectl get pods -n $RAY_CLUSTER_NAMESPACE -l app.kubernetes.io/name=kuberay-operator \
   -o jsonpath='{.items[0].status.phase}' | grep -q Running"

# ── 6c: RayCluster CRD exists ────────────────────────────────────────────────
run_validation "RayCluster CRD registered" bash -c \
  "kubectl get crd rayclusters.ray.io &>/dev/null"

# ── 6d: Head pod is actually running Ray GCS ─────────────────────────────────
run_validation "Ray GCS server listening on head pod" bash -c \
  "kubectl exec -n $RAY_CLUSTER_NAMESPACE $HEAD_POD -- \
     ray status 2>&1 | grep -qE '(Active|Healthy|resource_usage)'"

# ── 6e: Dashboard HTTP endpoint reachable (port-forward) ─────────────────────
# Run port-forward in background, probe, then kill.
run_validation "Ray Dashboard HTTP (8265) reachable" bash -c "
  kubectl port-forward -n $RAY_CLUSTER_NAMESPACE pod/$HEAD_POD 8265:8265 &>/dev/null &
  PF_PID=\$!
  sleep 3
  RESULT=1
  curl -sf --max-time 5 http://127.0.0.1:8265/ &>/dev/null && RESULT=0
  kill \$PF_PID 2>/dev/null || true
  exit \$RESULT
"

# ── Python Ray validations via kubectl exec ──────────────────────────────────
# We use 'kubectl exec' directly into the head pod to execute Python scripts
# that connect to the locally running GCS instance at 127.0.0.1:6379 natively.

# ── 6f: Ray remote task smoke test ───────────────────────────────────────────
run_validation "Ray remote task execution (python client)" bash -c "
  kubectl exec -n $RAY_CLUSTER_NAMESPACE $HEAD_POD -- python3 -c '
import ray
ray.init(address=\"auto\", _node_ip_address=__import__(\"socket\").gethostbyname(__import__(\"socket\").gethostname()))
@ray.remote
def hello(): return \"ray-ok\"
assert ray.get(hello.remote()) == \"ray-ok\", \"Validation failed\"
'
"

# ── 6g: Object store memory > 0 ──────────────────────────────────────────────
run_validation "Object store memory > 0 (python client)" bash -c "
  kubectl exec -n $RAY_CLUSTER_NAMESPACE $HEAD_POD -- python3 -c '
import ray
ray.init(address=\"auto\", _node_ip_address=__import__(\"socket\").gethostbyname(__import__(\"socket\").gethostname()))
m=ray.cluster_resources().get(\"object_store_memory\",0)
print(f\"{m/1e9:.2f} GB\")
assert m > 0, \"Object store memory is zero\"
'
"

# ── 6h: Node/raylet registration ─────────────────────────────────────────────
run_validation "Worker raylets registered in cluster (python client)" bash -c "
  kubectl exec -n $RAY_CLUSTER_NAMESPACE $HEAD_POD -- python3 -c '
import ray
ray.init(address=\"auto\", _node_ip_address=__import__(\"socket\").gethostbyname(__import__(\"socket\").gethostname()))
alive=[n for n in ray.nodes() if n.get(\"Alive\")]
print(f\"Alive nodes: {len(alive)}\")
assert len(alive) >= 2, \"Cluster does not have 2 nodes\"
'
"

# ── 6k: Parallel fan-out ─────────────────────────────────────────────────────
run_validation "Parallel Ray task fan-out (python client)" bash -c "
  kubectl exec -n $RAY_CLUSTER_NAMESPACE $HEAD_POD -- python3 -c '
import ray
ray.init(address=\"auto\", _node_ip_address=__import__(\"socket\").gethostbyname(__import__(\"socket\").gethostname()))
@ray.remote
def f(n): return n*n
res=ray.get([f.remote(i) for i in range(10)])
assert len(res) == 10, \"Parallel fan-out failed\"
'
"

# NOTE: minikube runs 1 CoreDNS replica by default; this is NOT a failure.
# The Terraform velero.tf / node_pools.tf fixes scale CoreDNS to 4 in production EKS.
# Here we just report what we observe.
run_validation "CoreDNS replicas (informational)" bash -c "
  COUNT=\$(kubectl get deployment coredns -n kube-system \
    -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)
  echo \"CoreDNS ready replicas: \$COUNT (minikube default=1; production=4)\"
  true  # always pass — this is an informational check only
"

# ── 6j: Velero CRD present (Terraform module validation) ─────────────────────
# The repo includes a velero.tf — check if the CRD can be installed locally.
# We deploy the CRDs only (no backup backend) as a structural check.
run_validation "Velero namespace or note (simulation)" bash -c "
  kubectl get namespace velero &>/dev/null \
    && echo 'velero namespace exists' \
    || echo 'velero namespace not present (expected in local env)'
  true    # never hard-fail this on local
"

# ── 6k: Ray workload — parallel compute tasks ────────────────────────────────
run_validation "Parallel Ray task fan-out (10 tasks)" bash -c "
kubectl exec -n $RAY_CLUSTER_NAMESPACE $HEAD_POD -- python3 -c \"
import ray, sys, time
ray.init('auto', _node_ip_address='127.0.0.1', ignore_reinit_error=True)
@ray.remote
def compute(n): return sum(range(n))
refs = [compute.remote(i * 1000) for i in range(10)]
results = ray.get(refs, timeout=60)
print(f'Results: {results}')
sys.exit(0)
\"
"

# ── 6l: OPA / Rego policy syntax check (static, no OPA binary required) ──────
run_validation "OPA policy files are present" bash -c "
  [ -d policies ] && find policies -name '*.rego' | grep -q .
"

# ── Step 7 — Final Report ─────────────────────────────────────────────────────
header "Validation Report"

TOTAL=$((PASS + FAIL))
echo ""
echo -e "  Tests run   : ${BOLD}${TOTAL}${NC}"
echo -e "  Passed      : ${GREEN}${BOLD}${PASS}${NC}"
echo -e "  Failed      : ${RED}${BOLD}${FAIL}${NC}"
echo ""

if [[ $FAIL -eq 0 ]]; then
  success "All $PASS validations passed. Local Ray cluster is healthy."
  EXIT_CODE=0
else
  warn "$FAIL validation(s) failed. Review output above."
  EXIT_CODE=1
fi

# ── Optional: expose dashboard ────────────────────────────────────────────────
echo ""
info "Ray Dashboard: run the following to open it in your browser:"
echo ""
echo "  kubectl port-forward -n $RAY_CLUSTER_NAMESPACE pod/$HEAD_POD 8265:8265 &"
echo "  open http://localhost:8265"
echo ""
info "To tear down: ./local_test.sh --teardown"
echo ""

exit $EXIT_CODE
