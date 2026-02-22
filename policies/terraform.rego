# Terraform Infrastructure Policy
# OPA policy for governance and compliance

package terraform

import future.keywords.if
import future.keywords.in

# Default deny
default allow = false

# Maximum allowed nodes per node group
max_nodes_per_group := 20

# Maximum GPU nodes allowed
max_gpu_nodes := 10

# Allowed regions (cost optimization)
allowed_regions := [
    "us-east-1",
    "us-east-2",
    "us-west-2",
    "eu-west-1"
]

# Allowed instance types
allowed_cpu_instance_types := [
    "t3.medium",
    "t3.large",
    "t3.xlarge",
    "m5.large",
    "m5.xlarge",
    "m5.2xlarge",
    "m5.4xlarge"
]

allowed_gpu_instance_types := [
    "g4dn.xlarge",
    "g4dn.2xlarge",
    "g4dn.4xlarge",
    "p3.2xlarge"
]

# Deny if region is not allowed
deny[msg] {
    input.resource_changes[_].type == "aws_eks_cluster"
    resource := input.resource_changes[_]
    region := input.variables.region.value
    not region in allowed_regions
    msg := sprintf("Region '%s' is not allowed. Must be one of: %v", [region, allowed_regions])
}

# Deny if CPU node count exceeds maximum
deny[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    contains(resource.name, "cpu")
    max_size := resource.change.after.scaling_config[0].max_size
    max_size > max_nodes_per_group
    msg := sprintf("CPU node group max size (%d) exceeds limit (%d)", [max_size, max_nodes_per_group])
}

# Deny if GPU node count exceeds maximum
deny[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    contains(resource.name, "gpu")
    max_size := resource.change.after.scaling_config[0].max_size
    max_size > max_gpu_nodes
    msg := sprintf("GPU node group max size (%d) exceeds limit (%d)", [max_size, max_gpu_nodes])
}

# Deny if using disallowed CPU instance type
deny[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    contains(resource.name, "cpu")
    instance_types := resource.change.after.instance_types
    instance_type := instance_types[_]
    not instance_type in allowed_cpu_instance_types
    msg := sprintf("CPU instance type '%s' is not allowed. Must be one of: %v", [instance_type, allowed_cpu_instance_types])
}

# Deny if using disallowed GPU instance type
deny[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    contains(resource.name, "gpu")
    instance_types := resource.change.after.instance_types
    instance_type := instance_types[_]
    not instance_type in allowed_gpu_instance_types
    msg := sprintf("GPU instance type '%s' is not allowed. Must be one of: %v", [instance_type, allowed_gpu_instance_types])
}

# Require encryption for EBS volumes
deny[msg] {
    input.resource_changes[_].type == "aws_launch_template"
    resource := input.resource_changes[_]
    block_devices := resource.change.after.block_device_mappings
    device := block_devices[_]
    not device.ebs[0].encrypted
    msg := "EBS volumes must be encrypted"
}

# Require tags on all resources
required_tags := ["ManagedBy", "Environment", "Repository"]

deny[msg] {
    input.resource_changes[_].type in ["aws_eks_cluster", "aws_eks_node_group"]
    resource := input.resource_changes[_]
    tags := object.get(resource.change.after, "tags", {})
    required_tag := required_tags[_]
    not tags[required_tag]
    msg := sprintf("Resource '%s' missing required tag: '%s'", [resource.address, required_tag])
}

# Require VPC endpoint access controls
deny[msg] {
    input.resource_changes[_].type == "aws_eks_cluster"
    resource := input.resource_changes[_]
    vpc_config := resource.change.after.vpc_config[0]
    vpc_config.endpoint_public_access == true
    not vpc_config.endpoint_private_access == true
    msg := "EKS cluster must have private endpoint access enabled when public access is enabled"
}

# Require CloudWatch logging
deny[msg] {
    input.resource_changes[_].type == "aws_eks_cluster"
    resource := input.resource_changes[_]
    log_types := object.get(resource.change.after, "enabled_cluster_log_types", [])
    count(log_types) == 0
    msg := "EKS cluster must have CloudWatch logging enabled"
}

# Require IMDSv2 for EC2 instances
deny[msg] {
    input.resource_changes[_].type == "aws_launch_template"
    resource := input.resource_changes[_]
    metadata := resource.change.after.metadata_options[0]
    metadata.http_tokens != "required"
    msg := "Launch templates must require IMDSv2 (http_tokens = required)"
}

# Storage limits
max_storage_size_gb := 500

deny[msg] {
    input.resource_changes[_].type == "aws_launch_template"
    resource := input.resource_changes[_]
    block_devices := resource.change.after.block_device_mappings
    device := block_devices[_]
    volume_size := device.ebs[0].volume_size
    volume_size > max_storage_size_gb
    msg := sprintf("Volume size (%d GB) exceeds maximum allowed (%d GB)", [volume_size, max_storage_size_gb])
}

# Cost optimization: Require autoscaling
deny[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    scaling := resource.change.after.scaling_config[0]
    scaling.min_size == scaling.max_size
    msg := sprintf("Node group '%s' has fixed size. Enable autoscaling by setting min_size < max_size", [resource.name])
}

# Security: Require private subnets for node groups
deny[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    subnet_ids := resource.change.after.subnet_ids
    subnet_id := subnet_ids[_]
    contains(subnet_id, "public")
    msg := sprintf("Node group must use private subnets, not public subnet: %s", [subnet_id])
}

# Allow if no denials
allow if {
    count(deny) == 0
}

# Warnings (non-blocking)
warn[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    desired := resource.change.after.scaling_config[0].desired_size
    max_size := resource.change.after.scaling_config[0].max_size
    desired == max_size
    msg := sprintf("Warning: Node group '%s' desired size equals max size. This prevents scale-up.", [resource.name])
}

warn[msg] {
    input.resource_changes[_].type == "aws_eks_node_group"
    resource := input.resource_changes[_]
    contains(resource.name, "gpu")
    min_size := resource.change.after.scaling_config[0].min_size
    min_size > 0
    msg := sprintf("Warning: GPU node group has min_size > 0. Consider setting to 0 for cost savings when idle.", [])
}

# Test cases
test_deny_invalid_region if {
    deny["Region 'ap-south-1' is not allowed. Must be one of: [\"us-east-1\", \"us-east-2\", \"us-west-2\", \"eu-west-1\"]"] with input as {
        "resource_changes": [{
            "type": "aws_eks_cluster",
            "name": "test-cluster"
        }],
        "variables": {
            "region": {"value": "ap-south-1"}
        }
    }
}

test_allow_valid_region if {
    count(deny) == 0 with input as {
        "resource_changes": [],
        "variables": {
            "region": {"value": "us-east-1"}
        }
    }
}
