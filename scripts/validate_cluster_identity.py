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


def check_kubeconfig_exists():
    """Check if kubeconfig file exists and return the path."""
    # Check KUBECONFIG env var first
    kubeconfig_path = os.environ.get('KUBECONFIG')

    if kubeconfig_path:
        # KUBECONFIG can be a colon-separated list of paths
        paths = kubeconfig_path.split(':')
        for path in paths:
            if os.path.exists(path):
                return path
        # If none of the paths exist, report the first one
        return None, paths[0]

    # Fall back to default location
    default_path = os.path.expanduser('~/.kube/config')
    if os.path.exists(default_path):
        return default_path

    return None, default_path


def get_cluster_fingerprint(context_name=None):
    """Generates a stable fingerprint for the current Kubernetes cluster."""
    try:
        # Check if kubeconfig file exists
        kubeconfig_result = check_kubeconfig_exists()
        if isinstance(kubeconfig_result, tuple):
            # File doesn't exist
            _, missing_path = kubeconfig_result
            raise FileNotFoundError(
                f"Kubeconfig file not found at: {missing_path}\n"
                f"Please ensure your Kubernetes configuration is set up correctly.\n"
                f"You may need to run: aws eks update-kubeconfig --name <cluster-name> --region <region>"
            )

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

    except FileNotFoundError as e:
        # Handle both kubectl not found and kubeconfig not found
        error_msg = str(e)
        if "kubectl" in error_msg.lower() and "kubeconfig" not in error_msg.lower():
            error_msg = "kubectl not found in PATH."
        return {"status": "error", "message": error_msg}
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
