package terraform

import rego.v1

# ---------------------------------------------------------------------------
# OPA Unit Tests for Cost Governance
# ---------------------------------------------------------------------------

# Helper for valid base input that satisfies terraform.rego
valid_base_input := {
    "variables": {"region": {"value": "us-east-1"}},
    "resource_changes": []
}

test_expensive_instance_denied if {
    mock_input := object.union(valid_base_input, {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "name": "ml-workers",
            "change": {"after": {
                "instance_types": ["p3.8xlarge"],
                "tags": {"ManagedBy": "T", "Environment": "D", "Repository": "R"},
                "scaling_config": [{"desired_size": 1, "min_size": 1, "max_size": 2}],
                "subnet_ids": ["subnet-private-1"]
            }}
        }
    ]})
    d := deny with input as mock_input
    some msg in d
    contains(msg, "Expensive instance type 'p3.8xlarge'")
}

test_standard_instance_allowed if {
    mock_input := object.union(valid_base_input, {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "name": "ml-workers-cpu",
            "change": {"after": {
                "instance_types": ["m5.xlarge"],
                "capacity_type": "SPOT",
                "scaling_config": [{"desired_size": 2, "min_size": 1, "max_size": 5}],
                "subnet_ids": ["subnet-private-1"],
                "tags": {"ManagedBy": "T", "Environment": "D", "Repository": "R"}
            }}
        }
    ]})
    d := deny with input as mock_input
    # We expect 0 denials from both cost_governance and terraform.rego
    count(d) == 0
}

test_gpu_on_demand_warns if {
    mock_input := object.union(valid_base_input, {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "name": "ml-workers-gpu",
            "change": {"after": {
                "instance_types": ["g4dn.xlarge"],
                "capacity_type": "ON_DEMAND",
                "tags": {"ManagedBy": "T", "Environment": "D", "Repository": "R"},
                "scaling_config": [{"desired_size": 1, "min_size": 1, "max_size": 2}],
                "subnet_ids": ["subnet-private-1"]
            }}
        }
    ]})
    w := warn with input as mock_input
    some msg in w
    contains(msg, "ON_DEMAND capacity")
}

test_budget_limit_denied if {
    mock_input := object.union(valid_base_input, {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "name": "ml-workers-cpu",
            "change": {"after": {
                "instance_types": ["m5.xlarge"],
                "scaling_config": [{"desired_size": 25, "min_size": 1, "max_size": 30}],
                "subnet_ids": ["subnet-private-1"],
                "tags": {"ManagedBy": "T", "Environment": "D", "Repository": "R"}
            }}
        }
    ]})
    d := deny with input as mock_input
    some msg in d
    contains(msg, "exceeds the safety limit of 20")
}
