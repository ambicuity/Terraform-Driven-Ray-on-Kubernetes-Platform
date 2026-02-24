# CPU Worker Node Group
resource "aws_eks_node_group" "cpu_workers" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-cpu-workers"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = var.subnet_ids
  instance_types  = var.cpu_node_instance_types
  ami_type        = "AL2023_ARM_64_STANDARD"

  scaling_config {
    desired_size = var.cpu_node_desired_size
    max_size     = var.cpu_node_max_size
    min_size     = var.cpu_node_min_size
  }

  capacity_type = var.cpu_capacity_type

  update_config {
    max_unavailable = 1
  }

  labels = {
    role                   = "cpu-worker"
    workload-type          = "general"
    "ray.io/node-type"     = "worker"
    "ray.io/resource-type" = "cpu"
    managed-by             = "github-app"
  }

  tags = {
    Name                                            = "${var.cluster_name}-cpu-workers"
    "k8s.io/cluster-autoscaler/${var.cluster_name}" = "owned"
    "k8s.io/cluster-autoscaler/enabled"             = var.enable_cluster_autoscaler ? "true" : "false"
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [scaling_config[0].desired_size]
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_AmazonEKSWorkerNodePolicy,
    aws_iam_role_policy_attachment.node_AmazonEKS_CNI_Policy,
    aws_iam_role_policy_attachment.node_AmazonEC2ContainerRegistryReadOnly,
  ]
}

# Launch Template for CPU Workers (for advanced configuration)
resource "aws_launch_template" "cpu_workers" {
  name_prefix = "${var.cluster_name}-cpu-"
  description = "Launch template for CPU worker nodes"

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 100
      volume_type           = "gp3"
      iops                  = 3000
      throughput            = 125
      delete_on_termination = true
      encrypted             = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name      = "${var.cluster_name}-cpu-worker"
      NodeGroup = "cpu-workers"
      ManagedBy = "github-app"
    }
  }

  user_data = base64encode(templatefile("${path.module}/user-data.sh", {
    cluster_name     = var.cluster_name
    cluster_endpoint = aws_eks_cluster.main.endpoint
    cluster_ca       = aws_eks_cluster.main.certificate_authority[0].data
    node_group_name  = "cpu-workers"
  }))
}

# GPU Worker Node Group
resource "aws_eks_node_group" "gpu_workers" {
  count = var.enable_gpu_nodes ? 1 : 0

  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-gpu-workers"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = var.subnet_ids
  instance_types  = var.gpu_node_instance_types

  scaling_config {
    desired_size = var.gpu_node_desired_size
    max_size     = var.gpu_node_max_size
    min_size     = var.gpu_node_min_size
  }

  capacity_type = var.gpu_capacity_type

  update_config {
    max_unavailable = 1
  }

  labels = {
    role                   = "gpu-worker"
    workload-type          = "gpu-intensive"
    "ray.io/node-type"     = "worker"
    "ray.io/resource-type" = "gpu"
    "nvidia.com/gpu"       = "true"
    managed-by             = "github-app"
  }

  # Taint GPU nodes to prevent non-GPU workloads
  taint {
    key    = "nvidia.com/gpu"
    value  = "true"
    effect = "NO_SCHEDULE"
  }

  tags = {
    Name                                            = "${var.cluster_name}-gpu-workers"
    "k8s.io/cluster-autoscaler/${var.cluster_name}" = "owned"
    "k8s.io/cluster-autoscaler/enabled"             = var.enable_cluster_autoscaler ? "true" : "false"
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [scaling_config[0].desired_size]
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_AmazonEKSWorkerNodePolicy,
    aws_iam_role_policy_attachment.node_AmazonEKS_CNI_Policy,
    aws_iam_role_policy_attachment.node_AmazonEC2ContainerRegistryReadOnly,
  ]
}

# Launch Template for GPU Workers
resource "aws_launch_template" "gpu_workers" {
  count = var.enable_gpu_nodes ? 1 : 0

  name_prefix = "${var.cluster_name}-gpu-"
  description = "Launch template for GPU worker nodes"

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 200
      volume_type           = "gp3"
      iops                  = 3000
      throughput            = 125
      delete_on_termination = true
      encrypted             = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name       = "${var.cluster_name}-gpu-worker"
      NodeGroup  = "gpu-workers"
      ManagedBy  = "github-app"
      GPUEnabled = "true"
    }
  }

  user_data = base64encode(templatefile("${path.module}/user-data-gpu.sh", {
    cluster_name     = var.cluster_name
    cluster_endpoint = aws_eks_cluster.main.endpoint
    cluster_ca       = aws_eks_cluster.main.certificate_authority[0].data
    node_group_name  = "gpu-workers"
  }))
}

# Cluster Autoscaler IAM Policy
# tfsec:ignore:aws-iam-no-policy-wildcards
# checkov:skip=CKV_AWS_111: Autoscaler requires write access for node scaling
# checkov:skip=CKV_AWS_355: Resource wildcard required for autoscaling
resource "aws_iam_policy" "cluster_autoscaler" {
  count       = var.enable_cluster_autoscaler ? 1 : 0
  name_prefix = "${var.cluster_name}-autoscaler-"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeScalingActivities",
          "autoscaling:DescribeTags",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeLaunchTemplateVersions"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup",
          "ec2:DescribeImages",
          "ec2:GetInstanceTypesFromInstanceRequirements",
          "eks:DescribeNodegroup"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM Role for Cluster Autoscaler (IRSA)
resource "aws_iam_role" "cluster_autoscaler" {
  count       = var.enable_cluster_autoscaler ? 1 : 0
  name_prefix = "${var.cluster_name}-autoscaler-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(local.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:kube-system:cluster-autoscaler"
          "${replace(local.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  count      = var.enable_cluster_autoscaler ? 1 : 0
  policy_arn = aws_iam_policy.cluster_autoscaler[0].arn
  role       = aws_iam_role.cluster_autoscaler[0].name
}

# AWS Node Termination Handler (Spot Interruption) IAM Role (IRSA)
resource "aws_iam_role" "node_termination_handler" {
  count       = var.enable_gpu_nodes && var.gpu_capacity_type == "SPOT" ? 1 : 0
  name_prefix = "${var.cluster_name}-nth-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(local.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:kube-system:aws-node-termination-handler"
          "${replace(local.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "node_termination_handler" {
  count      = var.enable_gpu_nodes && var.gpu_capacity_type == "SPOT" ? 1 : 0
  policy_arn = "arn:aws:iam::aws:policy/AmazonSQSFullAccess" # NTH requires SQS access to read ASG termination events
  role       = aws_iam_role.node_termination_handler[0].name
}

# Problem #3 Fix: Add graceful drain hook to GPU spot nodes
resource "aws_autoscaling_lifecycle_hook" "ray_graceful_drain" {
  count                  = var.enable_gpu_nodes ? 1 : 0
  name                   = "${var.cluster_name}-ray-drain-hook"
  autoscaling_group_name = aws_eks_node_group.gpu_workers[0].resources[0].autoscaling_groups[0].name
  lifecycle_transition   = "autoscaling:EC2_INSTANCE_TERMINATING"
  heartbeat_timeout      = 300
  default_result         = "CONTINUE"
}
