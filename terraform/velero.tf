# AWS S3 Bucket for Velero Backups
resource "aws_s3_bucket" "velero_backups" {
  count  = var.enable_velero ? 1 : 0
  bucket = "${var.cluster_name}-velero-backups-${var.region}"

  # checkov:skip=CKV_AWS_144: Cross-region replication doubles storage costs
  # checkov:skip=CKV_AWS_18: Access logging creates unnecessary storage costs for automated backups
  # checkov:skip=CKV_AWS_300: Velero manages the lifecycle and retention of backups natively
  # checkov:skip=CKV2_AWS_61: Lifecycle configuration is managed by Velero naturally
  # checkov:skip=CKV2_AWS_62: Event notifications are unnecessary for automated backups
  tags = {
    Name        = "${var.cluster_name}-velero-backups-bucket"
    Service     = "Ray"
    Environment = "Production"
  }
}

resource "aws_s3_bucket_versioning" "velero_backups" {
  count  = var.enable_velero ? 1 : 0
  bucket = aws_s3_bucket.velero_backups[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "velero_backups" {
  count  = var.enable_velero ? 1 : 0
  bucket = aws_s3_bucket.velero_backups[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "velero_backups" {
  count  = var.enable_velero ? 1 : 0
  bucket = aws_s3_bucket.velero_backups[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# IAM Role for Velero (IRSA)
data "aws_iam_policy_document" "velero_trust" {
  count = var.enable_velero ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    condition {
      test     = "StringEquals"
      variable = "${replace(local.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:velero:velero-server"]
    }

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
  }
}

resource "aws_iam_role" "velero_irsa" {
  count              = var.enable_velero ? 1 : 0
  name               = "${var.cluster_name}-velero-irsa"
  assume_role_policy = data.aws_iam_policy_document.velero_trust[0].json
  tags = {
    Name        = "${var.cluster_name}-velero-irsa"
    Service     = "Ray"
    Environment = "Production"
  }
}

data "aws_iam_policy_document" "velero_s3_ebs" {
  count = var.enable_velero ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "ec2:DescribeVolumes",
      "ec2:DescribeSnapshots",
      "ec2:CreateTags",
      "ec2:CreateVolume",
      "ec2:CreateSnapshot",
      "ec2:DeleteSnapshot"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts"
    ]
    resources = ["${aws_s3_bucket.velero_backups[0].arn}/*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:ListBucket"
    ]
    resources = [aws_s3_bucket.velero_backups[0].arn]
  }
}

resource "aws_iam_role_policy" "velero_irsa_inline" {
  count  = var.enable_velero ? 1 : 0
  name   = "velero-s3-ebs-access"
  role   = aws_iam_role.velero_irsa[0].id
  policy = data.aws_iam_policy_document.velero_s3_ebs[0].json
}

# Velero Helm Release
resource "helm_release" "velero" {
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> fc85a72 (fix(ci): Format terraform and append changelog entry for PR #17)
  count            = var.enable_velero ? 1 : 0
  name             = "velero"
  repository       = "https://vmware-tanzu.github.io/helm-charts"
  chart            = "velero"
  namespace        = "velero"
<<<<<<< HEAD
  create_namespace = true
  version          = "5.1.3"
=======
  count      = var.enable_velero ? 1 : 0
  name       = "velero"
  repository = "https://vmware-tanzu.github.io/helm-charts"
  chart      = "velero"
  namespace  = "velero"
  create_namespace = true
  version    = "5.1.3"
>>>>>>> 355bad5 (feat(ha): Implement Phase 3 Disaster Recovery and Multi-AZ Autoscaling)
=======
  create_namespace = true
  version          = "5.1.3"
>>>>>>> fc85a72 (fix(ci): Format terraform and append changelog entry for PR #17)

  values = [
    <<-EOT
    configuration:
      provider: aws
      backupStorageLocation:
        - name: default
          provider: aws
          bucket: ${aws_s3_bucket.velero_backups[0].id}
          config:
            region: ${var.region}
      volumeSnapshotLocation:
        - name: default
          provider: aws
          config:
            region: ${var.region}
      
    credentials:
      useSecret: false

    serviceAccount:
      server:
        create: true
        name: velero-server
        annotations:
          eks.amazonaws.com/role-arn: "${aws_iam_role.velero_irsa[0].arn}"

    initContainers:
      - name: velero-plugin-for-aws
        image: velero/velero-plugin-for-aws:v1.8.0
        imagePullPolicy: IfNotPresent
        volumeMounts:
          - mountPath: /target
            name: plugins
            
    schedules:
      daily-cluster-backup:
        schedule: "${var.velero_backup_schedule}"
        template:
          ttl: "720h"
          includedNamespaces:
            - "ray-system"
            - "kuberay-operator"
            - "kube-system"
    EOT
  ]

  depends_on = [
    aws_iam_role.velero_irsa,
    aws_iam_role_policy.velero_irsa_inline
  ]
}
