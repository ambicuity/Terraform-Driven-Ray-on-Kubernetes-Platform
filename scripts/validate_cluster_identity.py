import sys
import hashlib
import json
import os
from kubernetes import client, config
from kubernetes.client.rest import ApiException

def get_cluster_fingerprint(context_name=None):
    """Generates a stable fingerprint for the current Kubernetes cluster."""
    try:
        if context_name:
            config.load_kube_config(context=context_name)
        else:
            config.load_kube_config()
            
        v1 = client.CoreV1Api()
        
        # 1. Verify reachability
        version_info = client.VersionApi().get_code()
        
        # 2. Extract cluster UID from the kube-system namespace
        kube_system = v1.read_namespace("kube-system")
        cluster_uid = kube_system.metadata.uid
        
        # 3. Get API endpoint context (approximate via client.configuration)
        cluster_name = "active-context"
        
        fingerprint = hashlib.sha256(f"{cluster_uid}".encode()).hexdigest()
        
        return {
            "status": "success",
            "cluster_name": cluster_name,
            "cluster_uid": cluster_uid,
            "fingerprint": fingerprint,
            "version": version_info.git_version
        }
        
    except config.ConfigException as e:
        return {"status": "error", "message": f"Kubeconfig error: {e}"}
    except ApiException as e:
        return {"status": "error", "message": f"K8s API error: Server might be defunct. Details: {e}"}
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
        print(f"❌ VALIDATION FAILED: Unable to communicate with the cluster.\nReason: {current_data['message']}")
        print("This often happens if the cluster was recreated but your kubeconfig contains stale credentials/endpoints.")
        sys.exit(1)
        
    print(f"✅ Connected to cluster.")
    print(f"   Kube-System UID: {current_data['cluster_uid']}")
    print(f"   K8s Version: {current_data['version']}")
    
    if previous_data:
        if previous_data["fingerprint"] != current_data["fingerprint"]:
            print(f"❌ IDENTITY MISMATCH DETECTED (STALE CACHE PREVENTION)")
            print(f"   Previous UID: {previous_data['cluster_uid']}")
            print(f"   Current UID:  {current_data['cluster_uid']}")
            print("The cluster has been recreated! Proceeding with a stale Kubernetes client will cause 504 Gateway Timeouts and silent drops.")
            print("Run `aws eks update-kubeconfig` and clear any local caches.")
            sys.exit(2)
        else:
            print("✅ Cluster identity matches cached fingerprint.")
            
    # Save new fingerprint
    with open(cache_file, "w") as f:
        json.dump(current_data, f)
        
    print("Validation successful. Cluster is healthy and identity is verified.")
    sys.exit(0)

if __name__ == "__main__":
    main()
