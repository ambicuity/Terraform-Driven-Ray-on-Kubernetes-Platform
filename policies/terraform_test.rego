package terraform

import rego.v1

launch_template(encrypted, http_tokens) := {
  "address": "aws_launch_template.gpu_workers",
  "type": "aws_launch_template",
  "change": {
    "after": {
      "metadata_options": [{"http_tokens": http_tokens}],
      "block_device_mappings": [{"ebs": [{"encrypted": encrypted}]}]
    }
  }
}

gpu_node_group(address, capacity_type, capacity_class) := {
  "address": address,
  "type": "aws_eks_node_group",
  "change": {
    "after": {
      "capacity_type": capacity_type,
      "labels": {
        "ray.io/resource-type": "gpu",
        "capacity-class": capacity_class
      },
      "instance_types": ["g4dn.xlarge"],
      "scaling_config": [{"desired_size": 0, "min_size": 0, "max_size": 1}]
    }
  }
}

test_launch_templates_require_imdsv2 if {
  mock_input := {"resource_changes": [launch_template(true, "optional")]}
  d := deny with input as mock_input
  some msg in d
  contains(msg, "must require IMDSv2")
}

test_launch_templates_require_encryption if {
  mock_input := {"resource_changes": [launch_template(false, "required")]}
  d := deny with input as mock_input
  some msg in d
  contains(msg, "must encrypt its root volume")
}

test_spot_gpu_requires_fallback if {
  mock_input := {
    "resource_changes": [
      launch_template(true, "required"),
      gpu_node_group("aws_eks_node_group.gpu_workers", "SPOT", "spot")
    ]
  }
  d := deny with input as mock_input
  some msg in d
  contains(msg, "paired with an On-Demand fallback")
}

test_spot_gpu_with_fallback_allowed if {
  mock_input := {
    "resource_changes": [
      launch_template(true, "required"),
      gpu_node_group("aws_eks_node_group.gpu_workers", "SPOT", "spot"),
      gpu_node_group("aws_eks_node_group.gpu_ondemand_fallback", "ON_DEMAND", "on-demand-fallback")
    ]
  }
  d := deny with input as mock_input
  count(d) == 0
}

test_public_endpoint_requires_private_access if {
  mock_input := {
    "resource_changes": [{
      "address": "aws_eks_cluster.main",
      "type": "aws_eks_cluster",
      "change": {
        "after": {
          "vpc_config": [{
            "endpoint_public_access": true,
            "endpoint_private_access": false
          }]
        }
      }
    }]
  }
  d := deny with input as mock_input
  some msg in d
  contains(msg, "private endpoint access enabled")
}
