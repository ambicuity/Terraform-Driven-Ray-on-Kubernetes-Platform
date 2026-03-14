package terraform

import rego.v1

valid_base_input := {
  "variables": {"region": {"value": "us-east-1"}},
  "resource_changes": []
}

test_expensive_instance_denied if {
  mock_input := object.union(valid_base_input, {
    "resource_changes": [{
      "address": "aws_eks_node_group.ml_workers",
      "type": "aws_eks_node_group",
      "name": "ml-workers",
      "change": {
        "after": {
          "instance_types": ["p3.8xlarge"],
          "scaling_config": [{"desired_size": 1, "min_size": 0, "max_size": 2}],
          "labels": {"ray.io/resource-type": "gpu"}
        }
      }
    }]
  })
  d := deny with input as mock_input
  some msg in d
  contains(msg, "Expensive instance type 'p3.8xlarge'")
}

test_standard_instance_allowed if {
  mock_input := object.union(valid_base_input, {
    "resource_changes": [{
      "address": "aws_eks_node_group.ml_workers",
      "type": "aws_eks_node_group",
      "name": "ml-workers-cpu",
      "change": {
        "after": {
          "instance_types": ["m5.xlarge"],
          "capacity_type": "ON_DEMAND",
          "scaling_config": [{"desired_size": 2, "min_size": 1, "max_size": 5}],
          "labels": {"ray.io/resource-type": "cpu"}
        }
      }
    }]
  })
  d := deny with input as mock_input
  count(d) == 0
}

test_budget_limit_denied if {
  mock_input := object.union(valid_base_input, {
    "resource_changes": [{
      "address": "aws_eks_node_group.ml_workers",
      "type": "aws_eks_node_group",
      "name": "ml-workers-cpu",
      "change": {
        "after": {
          "instance_types": ["m5.xlarge"],
          "capacity_type": "ON_DEMAND",
          "scaling_config": [{"desired_size": 25, "min_size": 1, "max_size": 30}],
          "labels": {"ray.io/resource-type": "cpu"}
        }
      }
    }]
  })
  d := deny with input as mock_input
  some msg in d
  contains(msg, "exceeds the safety limit of 20")
}
