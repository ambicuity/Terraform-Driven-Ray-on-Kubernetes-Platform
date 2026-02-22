# Cluster Outputs
output "cluster_id" {
  description = "EKS cluster ID"
  value       = aws_eks_cluster.main.id
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint URL"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_version" {
  description = "Kubernetes version"
  value       = aws_eks_cluster.main.version
}

output "cluster_arn" {
  description = "EKS cluster ARN"
  value       = aws_eks_cluster.main.arn
}

output "cluster_certificate_authority" {
  description = "Cluster CA certificate"
  value       = aws_eks_cluster.main.certificate_authority[0].data
  sensitive   = true
}

# Authentication
output "cluster_oidc_issuer_url" {
  description = "OIDC issuer URL for the cluster"
  value       = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --name ${aws_eks_cluster.main.name} --region ${var.region}"
}

output "kubeconfig_path" {
  description = "Suggested kubeconfig file path"
  value       = "~/.kube/config-${aws_eks_cluster.main.name}"
}

# Node Groups
output "cpu_node_group_id" {
  description = "CPU node group ID"
  value       = aws_eks_node_group.cpu_workers.id
}

output "cpu_node_group_status" {
  description = "CPU node group status"
  value       = aws_eks_node_group.cpu_workers.status
}

output "gpu_node_group_id" {
  description = "GPU node group ID"
  value       = var.enable_gpu_nodes ? aws_eks_node_group.gpu_workers[0].id : null
}

output "gpu_node_group_status" {
  description = "GPU node group status"
  value       = var.enable_gpu_nodes ? aws_eks_node_group.gpu_workers[0].status : null
}

# Security
output "cluster_security_group_id" {
  description = "Cluster security group ID"
  value       = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
}

output "node_security_group_id" {
  description = "Node security group ID"
  value       = aws_security_group.node.id
}

# IAM
output "cluster_iam_role_arn" {
  description = "Cluster IAM role ARN"
  value       = aws_iam_role.cluster.arn
}

output "node_iam_role_arn" {
  description = "Node IAM role ARN"
  value       = aws_iam_role.node.arn
}

# IRSA Roles
output "cluster_autoscaler_iam_role_arn" {
  description = "IAM Role ARN for the Cluster Autoscaler (IRSA)"
  value       = var.enable_cluster_autoscaler ? aws_iam_role.cluster_autoscaler[0].arn : null
}

output "node_termination_handler_iam_role_arn" {
  description = "IAM Role ARN for the AWS Node Termination Handler (IRSA)"
  value       = var.enable_gpu_nodes && var.gpu_capacity_type == "SPOT" ? aws_iam_role.node_termination_handler[0].arn : null
}

# Monitoring
output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = var.enable_cloudwatch_logs ? aws_cloudwatch_log_group.cluster[0].name : null
}

# Region
output "region" {
  description = "AWS region"
  value       = var.region
}

# Tags
output "resource_tags" {
  description = "Tags applied to all resources"
  value = merge(
    var.tags,
    {
      ManagedBy   = "github-app"
      Repository  = var.repo_name
      Commit      = var.commit_sha
      Environment = var.environment
    }
  )
}

# Cost Estimation
output "estimated_monthly_cost" {
  description = "Rough monthly cost estimate (USD)"
  value       = "Estimate: ${var.cpu_node_desired_size * 70 + (var.enable_gpu_nodes ? var.gpu_node_desired_size * 2160 : 0)} USD/month (approximate)"
}

# Access Instructions
output "access_instructions" {
  description = "Instructions to access the cluster"
  value       = <<-EOT
    1. Configure kubectl:
       aws eks update-kubeconfig --name ${aws_eks_cluster.main.name} --region ${var.region}
    
    2. Verify cluster access:
       kubectl cluster-info
       kubectl get nodes
    
    3. Access Ray dashboard:
       kubectl port-forward -n ray-system svc/ray-cluster-head-svc 8265:8265
       Open: http://localhost:8265
    
    4. Deploy Ray cluster:
       See GitHub Actions workflow for automated deployment
  EOT
}
