# Ray Cluster Policy
# OPA policy for Ray workload governance

package ray

import future.keywords.if
import future.keywords.in

# Default configurations
default allow = false

# Maximum resources per Ray worker
max_cpu_per_worker := 16
max_memory_gb_per_worker := 64
max_gpu_per_worker := 4

# Maximum total cluster resources
max_total_workers := 50
max_total_gpus := 20

# Minimum resource requests (prevent resource starvation)
min_cpu_request := 0.5
min_memory_gb_request := 0.5

# Required labels
required_labels := [
    "ray.io/node-type",
    "app"
]

# Deny if worker requests exceed maximum CPU
deny[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    cpu := to_number(worker_group.template.spec.containers[0].resources.requests.cpu)
    cpu > max_cpu_per_worker
    msg := sprintf("Worker group '%s' requests %d CPUs, exceeds limit of %d", [worker_group.groupName, cpu, max_cpu_per_worker])
}

# Deny if worker requests exceed maximum memory
deny[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    memory_str := worker_group.template.spec.containers[0].resources.requests.memory
    contains(memory_str, "Gi")
    memory_gb := to_number(trim_suffix(memory_str, "Gi"))
    memory_gb > max_memory_gb_per_worker
    msg := sprintf("Worker group '%s' requests %dGi memory, exceeds limit of %dGi", [worker_group.groupName, memory_gb, max_memory_gb_per_worker])
}

# Deny if total workers exceed limit
deny[msg] {
    input.kind == "RayCluster"
    total_max_workers := sum([w.maxReplicas | some w in input.spec.workerGroupSpecs])
    total_max_workers > max_total_workers
    msg := sprintf("Total max workers (%d) exceeds cluster limit (%d)", [total_max_workers, max_total_workers])
}

# Deny if GPU request exceeds limit per worker
deny[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    gpu := to_number(worker_group.template.spec.containers[0].resources.requests["nvidia.com/gpu"])
    gpu > max_gpu_per_worker
    msg := sprintf("Worker group '%s' requests %d GPUs, exceeds limit of %d", [worker_group.groupName, gpu, max_gpu_per_worker])
}

# Deny if total GPU count exceeds limit
deny[msg] {
    input.kind == "RayCluster"
    gpu_workers := [w | some w in input.spec.workerGroupSpecs; w.template.spec.containers[0].resources.requests["nvidia.com/gpu"]]
    total_gpus := sum([w.maxReplicas * to_number(w.template.spec.containers[0].resources.requests["nvidia.com/gpu"]) | some w in gpu_workers])
    total_gpus > max_total_gpus
    msg := sprintf("Total max GPUs (%d) exceeds cluster limit (%d)", [total_gpus, max_total_gpus])
}

# Deny if missing required labels
deny[msg] {
    input.kind == "RayCluster"
    labels := object.get(input.metadata, "labels", {})
    required_label := required_labels[_]
    not labels[required_label]
    msg := sprintf("RayCluster missing required label: '%s'", [required_label])
}

# Deny if resource requests are too small
deny[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    cpu := to_number(worker_group.template.spec.containers[0].resources.requests.cpu)
    cpu < min_cpu_request
    msg := sprintf("Worker group '%s' CPU request (%f) below minimum (%f)", [worker_group.groupName, cpu, min_cpu_request])
}

# Deny if memory requests are too small
deny[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    memory_str := worker_group.template.spec.containers[0].resources.requests.memory
    contains(memory_str, "Gi")
    memory_gb := to_number(trim_suffix(memory_str, "Gi"))
    memory_gb < min_memory_gb_request
    msg := sprintf("Worker group '%s' memory request (%fGi) below minimum (%fGi)", [worker_group.groupName, memory_gb, min_memory_gb_request])
}

# Require GPU tolerations for GPU workers
deny[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    gpu_requested := to_number(worker_group.template.spec.containers[0].resources.requests["nvidia.com/gpu"])
    gpu_requested > 0
    tolerations := object.get(worker_group.template.spec, "tolerations", [])
    not has_gpu_toleration(tolerations)
    msg := sprintf("Worker group '%s' requests GPU but missing GPU toleration", [worker_group.groupName])
}

has_gpu_toleration(tolerations) if {
    toleration := tolerations[_]
    toleration.key == "nvidia.com/gpu"
}

# Require resource limits match requests (QoS Guaranteed)
warn[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    requests := worker_group.template.spec.containers[0].resources.requests
    limits := worker_group.template.spec.containers[0].resources.limits
    requests.cpu != limits.cpu
    msg := sprintf("Warning: Worker group '%s' CPU requests != limits. Consider matching for QoS Guaranteed.", [worker_group.groupName])
}

# Warn if autoscaling disabled
warn[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    min_replicas := worker_group.minReplicas
    max_replicas := worker_group.maxReplicas
    min_replicas == max_replicas
    msg := sprintf("Warning: Worker group '%s' has fixed size. Enable autoscaling for cost optimization.", [worker_group.groupName])
}

# Warn if GPU nodes have minReplicas > 0
warn[msg] {
    input.kind == "RayCluster"
    worker_group := input.spec.workerGroupSpecs[_]
    gpu := to_number(worker_group.template.spec.containers[0].resources.requests["nvidia.com/gpu"])
    gpu > 0
    min_replicas := worker_group.minReplicas
    min_replicas > 0
    msg := sprintf("Warning: GPU worker group '%s' has minReplicas > 0. Set to 0 for cost savings when idle.", [worker_group.groupName])
}

# Allow if no denials
allow if {
    count(deny) == 0
}

# Helper function
to_number(str) = result if {
    is_string(str)
    result := to_number(trim_suffix(str, "m")) / 1000
} else = str if {
    is_number(str)
    result := str
}
