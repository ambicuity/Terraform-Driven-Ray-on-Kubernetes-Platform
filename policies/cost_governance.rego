package terraform

import rego.v1

expensive_gpu_types := {"p3.2xlarge", "p3.8xlarge", "p3.16xlarge", "g5.48xlarge"}

deny contains msg if {
  some i
  node_group := input.resource_changes[i]
  node_group.type == "aws_eks_node_group"
  instance_type := node_group.change.after.instance_types[_]
  expensive_gpu_types[instance_type]
  msg := sprintf("Deny: Expensive instance type '%s' detected in node group '%s'. Prefer g4dn or smaller GPU families unless approved by FinOps.", [instance_type, node_group.address])
}

deny contains msg if {
  total_cpu := sum([
    desired |
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_eks_node_group"
    instance_type := resource.change.after.instance_types[_]
    regex.match("^(m5|m6g)\\.", instance_type)
    desired := resource.change.after.scaling_config[0].desired_size
  ])
  total_cpu > 20
  msg := sprintf("Deny: Total desired CPU capacity (%d nodes) exceeds the safety limit of 20. Please reduce scale or request a budget override.", [total_cpu])
}
