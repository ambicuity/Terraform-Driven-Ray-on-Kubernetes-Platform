output "cluster_name" {
  description = "EKS cluster name"
  value       = module.ray_eks_cluster.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint URL"
  value       = module.ray_eks_cluster.cluster_endpoint
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = module.ray_eks_cluster.kubeconfig_command
}

output "velero_backup_bucket_name" {
  description = "The S3 bucket used for Velero backups in the complete example"
  value       = var.enable_velero ? aws_s3_bucket.velero_backups[0].id : null
}

output "velero_iam_role_arn" {
  description = "The IRSA role used by Velero in the complete example"
  value       = var.enable_velero ? aws_iam_role.velero_irsa[0].arn : null
}
