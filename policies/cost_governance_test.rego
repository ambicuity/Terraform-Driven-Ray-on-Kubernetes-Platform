package terraform

import rego.v1

# ---------------------------------------------------------------------------
# OPA Unit Tests for Cost Governance
# ---------------------------------------------------------------------------

test_expensive_instance_denied if {
    mock_input := {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {"instance_types": ["p3.8xlarge"]}}
        }
    ]}
    d := deny with input as mock_input
    some msg in d
    contains(msg, "Expensive instance type 'p3.8xlarge'")
}

test_standard_instance_allowed if {
    mock_input := {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {"instance_types": ["g4dn.xlarge"]}}
        }
    ]}
    d := deny with input as mock_input
    count(d) == 0
}

test_gpu_on_demand_warns if {
    mock_input := {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {
                "instance_types": ["g4dn.xlarge"],
                "capacity_type": "ON_DEMAND"
            }}
        }
    ]}
    w := warn with input as mock_input
    some msg in w
    contains(msg, "ON_DEMAND capacity")
}

test_budget_limit_denied if {
    mock_input := {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {
                "instance_types": ["m5.xlarge"],
                "scaling_config": [{"desired_size": 25}]
            }}
        }
    ]}
    d := deny with input as mock_input
    some msg in d
    contains(msg, "exceeds the safety limit of 20")
}
