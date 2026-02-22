# EBS CSI Driver IAM Role (IRSA)
resource "aws_iam_role" "ebs_csi" {
  count       = var.enable_ebs_csi_driver ? 1 : 0
  name_prefix = "${var.cluster_name}-ebs-csi-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.cluster.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
          "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  count      = var.enable_ebs_csi_driver ? 1 : 0
  policy_arn = aws_iam_policy.ebs_csi[0].arn
  role       = aws_iam_role.ebs_csi[0].name
}

# Install EBS CSI Driver Add-on
resource "aws_eks_addon" "ebs_csi" {
  count        = var.enable_ebs_csi_driver ? 1 : 0
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "aws-ebs-csi-driver"
  addon_version = "v1.25.0-eksbuild.1"
  
  service_account_role_arn = aws_iam_role.ebs_csi[0].arn

  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  tags = {
    Name       = "${var.cluster_name}-ebs-csi-driver"
    ManagedBy  = "terraform"
  }

  depends_on = [
    aws_eks_node_group.cpu_workers
  ]
}

# Storage Class for Ray Persistent Volumes
resource "kubernetes_storage_class" "ray_storage" {
  count = var.enable_ebs_csi_driver ? 1 : 0

  metadata {
    name = var.storage_class_name
    annotations = {
      "storageclass.kubernetes.io/is-default-class" = "false"
    }
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy        = "Delete"
  allow_volume_expansion = true
  volume_binding_mode   = "WaitForFirstConsumer"

  parameters = {
    type      = "gp3"
    iops      = "3000"
    throughput = "125"
    encrypted = "true"
    fsType    = "ext4"
  }

  depends_on = [aws_eks_addon.ebs_csi]
}

# Persistent Volume Claim for Ray Head Node
resource "kubernetes_persistent_volume_claim" "ray_head" {
  count = var.enable_ebs_csi_driver ? 1 : 0

  metadata {
    name      = "ray-head-storage"
    namespace = kubernetes_namespace.ray[0].metadata[0].name
    labels = {
      app       = "ray"
      component = "head"
    }
  }

  spec {
    access_modes = ["ReadWriteOnce"]
    storage_class_name = kubernetes_storage_class.ray_storage[0].metadata[0].name

    resources {
      requests = {
        storage = "50Gi"
      }
    }
  }

  depends_on = [kubernetes_storage_class.ray_storage]
}

# Persistent Volume Claim Template for Ray Workers
resource "kubernetes_persistent_volume_claim" "ray_worker" {
  count = var.enable_ebs_csi_driver ? 1 : 0

  metadata {
    name      = "ray-worker-storage-template"
    namespace = kubernetes_namespace.ray[0].metadata[0].name
    labels = {
      app       = "ray"
      component = "worker"
    }
  }

  spec {
    access_modes = ["ReadWriteOnce"]
    storage_class_name = kubernetes_storage_class.ray_storage[0].metadata[0].name

    resources {
      requests = {
        storage = "20Gi"
      }
    }
  }

  depends_on = [kubernetes_storage_class.ray_storage]
}

# S3 Bucket for Ray Artifacts (Optional)
resource "aws_s3_bucket" "ray_artifacts" {
  bucket_prefix = "${var.cluster_name}-ray-artifacts-"

  tags = {
    Name       = "${var.cluster_name}-ray-artifacts"
    Purpose    = "ray-job-artifacts"
    ManagedBy  = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "ray_artifacts" {
  bucket = aws_s3_bucket.ray_artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ray_artifacts" {
  bucket = aws_s3_bucket.ray_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "ray_artifacts" {
  bucket = aws_s3_bucket.ray_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "ray_artifacts" {
  bucket = aws_s3_bucket.ray_artifacts.id

  rule {
    id     = "expire-old-artifacts"
    status = "Enabled"

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

# IAM Policy for Ray to access S3
resource "aws_iam_policy" "ray_s3_access" {
  name_prefix = "${var.cluster_name}-ray-s3-"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.ray_artifacts.arn,
          "${aws_s3_bucket.ray_artifacts.arn}/*"
        ]
      }
    ]
  })
}

# IAM Role for Ray Pods (IRSA)
resource "aws_iam_role" "ray_pods" {
  name_prefix = "${var.cluster_name}-ray-pods-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.cluster.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:sub" = "system:serviceaccount:${var.ray_namespace}:ray-worker"
          "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ray_s3_access" {
  policy_arn = aws_iam_policy.ray_s3_access.arn
  role       = aws_iam_role.ray_pods.name
}

# Kubernetes Service Account for Ray
resource "kubernetes_service_account" "ray_worker" {
  metadata {
    name      = "ray-worker"
    namespace = kubernetes_namespace.ray[0].metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.ray_pods.arn
    }
  }

  depends_on = [aws_eks_cluster.main]
}
