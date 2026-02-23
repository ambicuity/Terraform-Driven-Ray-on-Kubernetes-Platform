# Basic terraform test configuration
mock_provider "aws" {}
mock_provider "kubernetes" {}
mock_provider "helm" {}
mock_provider "tls" {}
variables {
  cluster_name = "test-cluster"
  region       = "us-east-1"
  vpc_id       = "vpc-12345"
  subnet_ids   = ["subnet-12345", "subnet-67890"]
}

run "validate_inputs" {
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
    condition     = aws_eks_node_group.gpu_workers[0].capacity_type == "SPOT"
    error_message = "GPU nodes should default to SPOT"
  }
}
