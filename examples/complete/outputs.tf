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
