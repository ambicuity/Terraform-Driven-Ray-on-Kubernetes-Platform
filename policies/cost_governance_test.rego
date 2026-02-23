package terraform.cost

# ---------------------------------------------------------------------------
# OPA Unit Tests for Cost Governance
# ---------------------------------------------------------------------------

test_expensive_instance_denied {
    input := {"plan": {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {"instance_types": ["p3.8xlarge"]}}
        }
    ]}}
    count(deny) == 1
    contains(deny[_], "Expensive instance type 'p3.8xlarge'")
}

test_standard_instance_allowed {
    input := {"plan": {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {"instance_types": ["g4dn.xlarge"]}}
        }
    ]}}
    count(deny) == 0
}

test_gpu_on_demand_warns {
    input := {"plan": {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {
                "instance_types": ["g4dn.xlarge"],
                "capacity_type": "ON_DEMAND"
            }}
        }
    ]}}
    count(warn) == 1
    contains(warn[_], "ON_DEMAND capacity")
}

test_budget_limit_denied {
    input := {"plan": {"resource_changes": [
        {
            "address": "aws_eks_node_group.ml_workers",
            "type": "aws_eks_node_group",
            "change": {"after": {
                "instance_types": ["m5.xlarge"],
                "scaling_config": [{"desired_size": 25}]
            }}
        }
    ]}}
    count(deny) == 1
    contains(deny[_], "exceeds the safety limit of 20")
}
