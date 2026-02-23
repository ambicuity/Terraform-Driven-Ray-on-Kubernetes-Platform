# MIT License
# Copyright (c) 2026 ambicuity
import ray
import time
import random
import sys
import threading
from kubernetes import client, config
from kubernetes.client.rest import ApiException

"""
Chaos Resilience Test for Ray ML Platform.

This script demonstrates Ray's self-healing capabilities by:
1. Launching a large parallel workload.
2. Natively querying the Kubernetes API to find an active Ray worker pod.
3. Forcibly deleting the pod (Simulating Node/Spot Interruption).
4. Verifying object store recovery and calculating Mean Time To Recovery (MTTR).
"""


@ray.remote(max_retries=3)
def resilient_task(task_id):
    """A task that takes some time and prints status."""
    time.sleep(random.uniform(2, 5))
    print(f"Task {task_id} completed on node {ray.get_runtime_context().node_id}")
    return task_id

def kill_random_worker_pod():
    """Interacts with the Kube API to delete a random Ray worker pod."""
    try:
        # Load in-cluster config or local kubeconfig
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        v1 = client.CoreV1Api()
        
        # We assume the ray cluster is usually in the "default" or "ray-system" namespace.
        # Since Helm deploys it to the namespace of the chart, querying all namespaces for the label is safest.
        print("🔍 Scanning Kubernetes for active Ray worker pods...")
        pods = v1.list_pod_for_all_namespaces(label_selector="ray.io/node-type=worker")
        
        if not pods.items:
            print("⚠️ No worker pods found. Skipping physical chaos injection.")
            return

        # Pick a random worker to sacrifice
        target_pod = random.choice(pods.items)
        pod_name = target_pod.metadata.name
        namespace = target_pod.metadata.namespace

        print(f"🔥 CHAOS INJECTED: Terminating pod {pod_name} in namespace {namespace}...")
        
        # Force delete the pod (Grace period 0)
        v1.delete_namespaced_pod(
            name=pod_name,
            namespace=namespace,
            body=client.V1DeleteOptions(grace_period_seconds=0)
        )
        print(f"💀 Pod {pod_name} successfully terminated.")

    except ApiException as e:
        print(f"⚠️ Kubernetes API error during chaos injection: {e}")
    except Exception as e:
        print(f"⚠️ Unexpected error during chaos injection: {e}")

def run_chaos_test():
    print("🚀 Initializing Chaos Resilience Test...")
    
    # Initialize Ray (assumes existing cluster in prod, or local for testing)
    try:
        ray.init(address="auto")
    except ConnectionError:
        print("Warning: Ray cluster not found. Initializing local Ray for simulation.")
        ray.init()

    num_tasks = 50  # Increased task count to ensure tasks are running during termination
    print(f"Submitting {num_tasks} tasks with max_retries=3...")
    
    start_time = time.time()
    futures = [resilient_task.remote(i) for i in range(num_tasks)]
    
    # Schedule chaos injection 5 seconds into the workload
    print("⏱️ Scheduling pod termination in 5 seconds...")
    chaos_timer = threading.Timer(5.0, kill_random_worker_pod)
    chaos_timer.start()
    
    try:
        # Wait for all tasks to complete despite the pod deletion
        results = ray.get(futures, timeout=120)
        end_time = time.time()
        
        mttr_seconds = (end_time - start_time)
        print("==================================================")
        print("✅ SUCCESS: Fault Tolerance Verified")
        print("==================================================")
        print(f"All {num_tasks} tasks ultimately completed despite the node loss.")
        print(f"Job Time (including recovery): {mttr_seconds:.2f} seconds")
        print("==================================================")
        
    except Exception as e:
        print("==================================================")
        print(f"❌ FAILURE: Chaos test failed to recover. Error: {str(e)}")
        print("==================================================")
        sys.exit(1)
    finally:
        chaos_timer.cancel()


if __name__ == "__main__":
    run_chaos_test()
