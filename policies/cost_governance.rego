package terraform.cost

import rego.v1
import input.plan as tfplan

# ---------------------------------------------------------------------------
# FinOps Governance Policies
# ---------------------------------------------------------------------------

# Deny if any EKS node group is using expensive instance types without justification
deny contains msg if {
    some i
    node_group = tfplan.resource_changes[i]
    node_group.type == "aws_eks_node_group"
    
    # Check instance types
    instance_types := node_group.change.after.instance_types
    expensive_types := {"p3.2xlarge", "p3.8xlarge", "p3.16xlarge", "g5.48xlarge"}
    
    some t
    expensive_types[instance_types[t]]
    
    msg := sprintf("Deny: Expensive instance type '%s' detected in node group '%s'. Please use g4dn or m5 family unless approved by FinOps.", [instance_types[t], node_group.address])
}

# Warn if GPU nodes are requested in ON_DEMAND capacity
warn contains msg if {
    some i
    node_group = tfplan.resource_changes[i]
    node_group.type == "aws_eks_node_group"
    
    # Look for GPU labels or instance types
    instance_types := node_group.change.after.instance_types
    some t
    contains(instance_types[t], "g4dn")
    
    # Check capacity type
    node_group.change.after.capacity_type == "ON_DEMAND"
    
    msg := sprintf("Warning: GPU node group '%s' is using ON_DEMAND capacity. Consider switching to SPOT to save up to 70%%.", [node_group.address])
}

# Deny if total desired CPU capacity exceeds 20 nodes (Budget Guardrail)
deny contains msg if {
    total_cpu := sum([count | 
        some i
        resource := tfplan.resource_changes[i]
        resource.type == "aws_eks_node_group"
        # Only count m5 family (CPU nodes)
        some t
        contains(resource.change.after.instance_types[t], "m5")
        count := resource.change.after.scaling_config[0].desired_size
    ])
    
    total_cpu > 20
    
    msg := sprintf("Deny: Total desired CPU capacity (%d nodes) exceeds the safety limit of 20. Please reduce scale or request a budget override.", [total_cpu])
}
