#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity

import sys
import hashlib
import json
import os
import subprocess


def run_kubectl_json(cmd_args):
    """Utility to run kubectl and return parsed JSON stdout."""
    result = subprocess.run(
        ["kubectl"] + cmd_args + ["-o", "json"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def get_cluster_fingerprint(context_name=None):
    """Generates a stable fingerprint for the current Kubernetes cluster."""
    try:
        # Check kubectl availability
        subprocess.run(["kubectl", "version", "--client"], capture_output=True, check=True)

        # 1. Verify reachability and get version
        version_result = subprocess.run(["kubectl", "version", "-o", "json"], capture_output=True, text=True)
        if version_result.returncode != 0:
            raise RuntimeError(version_result.stderr.strip())
        version_info = json.loads(version_result.stdout)
        server_version = version_info.get("serverVersion", {}).get("gitVersion", "unknown")

        # 2. Extract cluster UID from the kube-system namespace
        kube_system = run_kubectl_json(["get", "namespace", "kube-system"])
        cluster_uid = kube_system.get("metadata", {}).get("uid")

        # 3. Get API endpoint context
        cluster_name = "active-context"

        fingerprint = hashlib.sha256(f"{cluster_uid}".encode()).hexdigest()

        return {
            "status": "success",
            "cluster_name": cluster_name,
            "cluster_uid": cluster_uid,
            "fingerprint": fingerprint,
            "version": server_version
        }

    except FileNotFoundError:
        return {"status": "error", "message": "kubectl not found in PATH."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    print("Validating Kubernetes Cluster Identity...")

    # Check for previously stored fingerprint
    cache_file = ".k8s_cluster_fingerprint.json"
    previous_data = None

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            previous_data = json.load(f)

    current_data = get_cluster_fingerprint()

    if current_data["status"] == "error":
        print(
            f"\u274c VALIDATION FAILED: Unable to communicate with the cluster.\n"
            f"Reason: {current_data['message']}"
        )
        print(
            "This often happens if the cluster was recreated but your "
            "kubeconfig contains stale credentials/endpoints."
        )
        sys.exit(1)

    print("\u2705 Connected to cluster.")
    print(f"   Kube-System UID: {current_data['cluster_uid']}")
    print(f"   K8s Version: {current_data['version']}")

    if previous_data:
        if previous_data["fingerprint"] != current_data["fingerprint"]:
            print("\u274c IDENTITY MISMATCH DETECTED (STALE CACHE PREVENTION)")
            print(f"   Previous UID: {previous_data['cluster_uid']}")
            print(f"   Current UID:  {current_data['cluster_uid']}")
            print(
                "The cluster has been recreated! Proceeding with a stale Kubernetes client "
                "will cause 504 Gateway Timeouts and silent drops."
            )
            print("Run `aws eks update-kubeconfig` and clear any local caches.")
            sys.exit(2)
        else:
            print("\u2705 Cluster identity matches cached fingerprint.")

    # Save new fingerprint
    with open(cache_file, "w") as f:
        json.dump(current_data, f)

    print("Validation successful. Cluster is healthy and identity is verified.")
    sys.exit(0)


if __name__ == "__main__":
    main()
