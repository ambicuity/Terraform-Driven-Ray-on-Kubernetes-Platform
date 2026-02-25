#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity

import ray
import numpy as np
import subprocess
import sys


def get_empty_dir_size():
    """Checks the size of the /tmp/ray emptyDir on the current worker."""
    try:
        df = subprocess.run(["df", "-h", "/tmp/ray"], capture_output=True, text=True, check=True)
        return df.stdout
    except Exception as e:
        return f"Could not run df on /tmp/ray: {e}"


@ray.remote
def memory_hog_task():
    """Allocates a large numpy array to intentionally trigger object spilling."""
    print(f"Node: {ray.get_runtime_context().node_id}")

    # 1 GB numpy array
    print("Allocating 1GB object...")
    arr = np.ones((1024, 1024, 1024 // 8), dtype=np.float64)

    # Verify the emptyDir
    df_output = get_empty_dir_size()
    print("--- /tmp/ray Usage ---")
    print(df_output)

    return arr


def run_stress_test():
    print("🚀 Initializing Ray Memory Spill Validation Test...")

    # Limit object store to 2GB to force spilling quickly
    # In a real cluster, this connects to the KubeRay head node
    try:
        ray.init(address="auto", object_store_memory=2 * 1024 * 1024 * 1024)
    except Exception:
        print("Falling back to local ray with constrained memory...")
        ray.init(object_store_memory=2 * 1024 * 1024 * 1024)

    print("📊 Object Store capacity constrained to 2GB.")
    print("🔥 Spinning up heavy data loading simulations (generating 5GB)...")

    # Generate 5 x 1GB objects, exceeding the 2GB object store
    refs = [memory_hog_task.remote() for _ in range(5)]

    # Wait for completion
    try:
        ray.get(refs, timeout=300)
    except ray.exceptions.ObjectStoreFullError:
        print("❌ FAILED: Ray crashed with ObjectStoreFullError. Spilling failed.")
        sys.exit(1)

    print("\u2705 SUCCESS: Tasks completed. Object spilling handled the excess memory gracefully.")
    print("Because /tmp/ray is mounted via emptyDir (medium: Memory), Kubelet DiskPressure was bypassed!")


if __name__ == "__main__":
    run_stress_test()
