# Terraform 1.5 discovers tests from the module root, so keep this file here.
mock_provider "aws" {}
mock_provider "tls" {}

variables {
  cluster_name = "test-cluster"
  region       = "us-east-1"
  vpc_id       = "vpc-12345"
  subnet_ids   = ["subnet-12345", "subnet-67890"]
}

run "spot_primary_creates_fallback" {
  command = plan

  assert {
    condition     = aws_eks_cluster.main.name == "test-cluster"
    error_message = "Cluster name did not match input variable"
  }

  assert {
    condition     = aws_eks_node_group.cpu_workers.capacity_type == "ON_DEMAND"
    error_message = "CPU nodes should default to ON_DEMAND"
  }

  assert {
    condition     = length(aws_eks_node_group.cpu_workers.launch_template) == 1
    error_message = "CPU node group should use the managed launch template"
  }

  assert {
    condition     = aws_eks_node_group.gpu_workers[0].capacity_type == "SPOT"
    error_message = "Primary GPU nodes should default to SPOT"
  }

  assert {
    condition     = length(aws_eks_node_group.gpu_workers[0].launch_template) == 1
    error_message = "Primary GPU node group should use the managed launch template"
  }

  assert {
    condition     = length(aws_eks_node_group.gpu_ondemand_fallback) == 1
    error_message = "Spot GPU clusters should create an On-Demand fallback node group by default"
  }

  assert {
    condition     = aws_eks_node_group.gpu_ondemand_fallback[0].capacity_type == "ON_DEMAND"
    error_message = "Fallback GPU nodes must always use ON_DEMAND capacity"
  }
}

run "disable_spot_fallback_explicitly" {
  command = plan

  variables {
    enable_gpu_ondemand_fallback = false
  }

  assert {
    condition     = length(aws_eks_node_group.gpu_ondemand_fallback) == 0
    error_message = "Fallback GPU node group should be removable when explicitly disabled"
  }
}

run "pure_ondemand_gpu_mode" {
  command = plan

  variables {
    gpu_capacity_type = "ON_DEMAND"
  }

  assert {
    condition     = aws_eks_node_group.gpu_workers[0].capacity_type == "ON_DEMAND"
    error_message = "Primary GPU node group should respect ON_DEMAND mode"
  }

  assert {
    condition     = length(aws_eks_node_group.gpu_ondemand_fallback) == 0
    error_message = "Fallback GPU node group should not be created for pure ON_DEMAND mode"
  }
}
