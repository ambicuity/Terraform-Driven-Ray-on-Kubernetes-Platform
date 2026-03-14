package terraform

import rego.v1

default allow = false

deny contains msg if {
  some i
  resource := input.resource_changes[i]
  resource.type == "aws_launch_template"
  metadata := resource.change.after.metadata_options[0]
  metadata.http_tokens != "required"
  msg := sprintf("Launch template '%s' must require IMDSv2 (http_tokens = required)", [resource.address])
}

deny contains msg if {
  some i
  resource := input.resource_changes[i]
  resource.type == "aws_launch_template"
  device := resource.change.after.block_device_mappings[_]
  not device.ebs[0].encrypted
  msg := sprintf("Launch template '%s' must encrypt its root volume", [resource.address])
}

deny contains msg if {
  some i
  resource := input.resource_changes[i]
  resource.type == "aws_eks_cluster"
  vpc_config := resource.change.after.vpc_config[0]
  vpc_config.endpoint_public_access
  not vpc_config.endpoint_private_access
  msg := "EKS clusters must keep private endpoint access enabled whenever public endpoint access is enabled"
}

deny contains msg if {
  has_spot_gpu_primary
  not has_gpu_ondemand_fallback
  msg := "SPOT GPU node groups must be paired with an On-Demand fallback node group."
}

has_spot_gpu_primary if {
  some i
  resource := input.resource_changes[i]
  resource.type == "aws_eks_node_group"
  resource.change.after.capacity_type == "SPOT"
  labels := object.get(resource.change.after, "labels", {})
  labels["ray.io/resource-type"] == "gpu"
}

has_gpu_ondemand_fallback if {
  some i
  resource := input.resource_changes[i]
  resource.type == "aws_eks_node_group"
  resource.change.after.capacity_type == "ON_DEMAND"
  labels := object.get(resource.change.after, "labels", {})
  labels["capacity-class"] == "on-demand-fallback"
}

allow if {
  count(deny) == 0
}
